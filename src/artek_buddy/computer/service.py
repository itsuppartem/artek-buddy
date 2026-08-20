from __future__ import annotations

import logging
import mimetypes
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from artek_buddy.auth import supervisor_token
from artek_buddy.computer.client import FakeSupervisorClient, SupervisorClient
from artek_buddy.computer.models import ComputerRecord
from artek_buddy.computer.screen import mint_novnc_url
from artek_buddy.config import Settings
from artek_buddy.contracts.domain import (
    Bot,
    ComputerFileContent,
    ComputerFileEntry,
    ComputerFileList,
    ComputerStatus,
    ScreenUrlResult,
    TakeoverResult,
)
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.uploads import remove_bot_inbox_copies

log = logging.getLogger("artek_buddy")

EXEC_TTL = timedelta(minutes=5)
_HOME_KEY = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_HOME_READ_BYTES = 2 * 1024 * 1024
MAX_HOME_DOWNLOAD_BYTES = 50 * 1024 * 1024


def wipe_computer_home(data_dir: Path, home_key: str) -> Path:
    if not _HOME_KEY.fullmatch(home_key):
        raise ComputerError("invalid home")
    root = (Path(data_dir) / "homes").resolve()
    path = (root / home_key).resolve()
    if path.parent != root:
        raise ComputerError("invalid home")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


class ComputerBusy(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class ComputerError(Exception):
    pass


class ComputerUnavailable(ComputerError):
    """The desktop is supposed to be reachable but the screen proxy cannot mint a URL."""


class ComputerService:
    def __init__(self, store: HistoryStore, settings: Settings, client: Any | None = None) -> None:
        self.store = store
        self.settings = settings
        if client is not None:
            self.client = client
        elif settings.sandbox_provider == "fake":
            self.client = FakeSupervisorClient()
        else:
            token = supervisor_token(settings.agent_http_token, settings.sandbox_supervisor_token)
            self.client = SupervisorClient(settings.sandbox_supervisor_url, token)

    def home_path(self, record: ComputerRecord) -> Path:
        path = Path(self.settings.agent_data_dir) / "homes" / record.home_key
        path.mkdir(parents=True, exist_ok=True)
        return path

    def status(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        busy = self.store.busy_bot_name(record, bot.id)
        return record.status_for(bot.id, bot.computer_mode, busy)

    def boot(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if record.scope == "team":
            busy = self.store.busy_bot_name(record, bot.id)
            if busy:
                raise ComputerBusy(busy)
            record.execution_bot_id = bot.id
            record.execution_run_id = new_id("boot")
            record.execution_lease_expires_at = isoformat_utc(datetime.now(timezone.utc) + EXEC_TTL)
        if record.state == "running" and record.provider_ref and self._box_alive(record.provider_ref):
            record = self._touch(record)
            self.store.save_computer(record)
            return self.status(bot)
        if record.provider_ref and not self._box_alive(record.provider_ref):
            log.warning("stale computer container %s, reprovisioning", record.provider_ref)
            record.provider_ref = None
        record.state = "booting"
        record.kind = "fake" if self.settings.sandbox_provider == "fake" else "docker"
        self.store.save_computer(record)
        try:
            box = self.client.provision(bot.id, record.home_key)
            record.provider_ref = box.id
            record.state = "running"
            record = self._touch(record)
            self.store.save_computer(record)
        except Exception as err:
            record.state = "error"
            self.store.save_computer(record)
            raise ComputerError(str(err)) from err
        return self.status(bot)

    def stop(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        busy = self.store.busy_bot_name(record, bot.id)
        if busy:
            raise ComputerBusy(busy)
        if record.provider_ref:
            try:
                self.client.stop(record.provider_ref)
            except Exception:
                log.exception("supervisor stop failed")
        record.state = "stopped"
        record.control_holder = "none"
        record.control_lease_id = None
        record.control_lease_expires_at = None
        record.control_bot_id = None
        record.execution_bot_id = None
        record.execution_run_id = None
        record.execution_lease_expires_at = None
        record.sleep_at = None
        record.home_revision = isoformat_utc()
        self.store.save_computer(record)
        return self.status(bot)

    def restart(self, bot: Bot) -> ComputerStatus:
        if self.store.has_active_run(bot.id):
            raise ComputerBusy(bot.name)
        self.stop(bot)
        return self.boot(bot)

    def reset(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if self.store.has_active_run(bot.id):
            raise ComputerBusy(bot.name)
        busy = self.store.busy_bot_name(record, bot.id)
        if busy:
            raise ComputerBusy(busy)
        self._destroy_box(record)
        return self.status(bot)

    def remove_bot_uploads(self, bot: Bot) -> None:
        """Drop this chat's inbox copies even when the Team home stays."""
        record = self.store.get_computer_for_bot(bot)
        artifacts = []
        listing = getattr(self.store, "list_artifacts", None)
        if callable(listing):
            artifacts = listing(bot.id)
        remove_bot_inbox_copies(
            self.home_path(record),
            Path(self.settings.agent_data_dir),
            bot.id,
            artifacts,
        )

    def release_for_deleted_bot(self, bot: Bot) -> None:
        """Drop this bot's box. Shared Team stays if another bot still uses it."""
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        others = 0
        if hasattr(self.store, "other_bots_using_computer"):
            others = int(self.store.other_bots_using_computer(record.id, bot.id))
        if others > 0:
            self._detach_bot(record, bot.id)
            return
        self._destroy_box(record)

    def reap_orphan_computers(self) -> int:
        """Destroy boxes that no bot points at (left behind by older deletes)."""
        if not hasattr(self.store, "list_orphan_computers"):
            return 0
        reaped = 0
        for record in self.store.list_orphan_computers():
            self._destroy_box(record)
            if hasattr(self.store, "delete_computer"):
                self.store.delete_computer(record.id)
            reaped += 1
        return reaped

    def _detach_bot(self, record: ComputerRecord, bot_id: str) -> ComputerRecord:
        changed = False
        if record.execution_bot_id == bot_id:
            record.execution_bot_id = None
            record.execution_run_id = None
            record.execution_lease_expires_at = None
            changed = True
        if record.control_bot_id == bot_id:
            record.control_holder = "none"
            record.control_lease_id = None
            record.control_lease_expires_at = None
            record.control_bot_id = None
            changed = True
        if changed:
            self.store.save_computer(record)
        return record

    def _destroy_box(self, record: ComputerRecord) -> ComputerRecord:
        if record.provider_ref:
            try:
                self.client.destroy(record.provider_ref)
            except Exception:
                log.exception("supervisor destroy failed")
        try:
            wipe_computer_home(Path(self.settings.agent_data_dir), record.home_key)
        except ComputerError:
            log.exception("failed to wipe computer home %s", record.home_key)
        record.provider_ref = None
        record.state = "stopped"
        record.control_holder = "none"
        record.control_lease_id = None
        record.control_lease_expires_at = None
        record.control_bot_id = None
        record.execution_bot_id = None
        record.execution_run_id = None
        record.execution_lease_expires_at = None
        record.sleep_at = None
        record.home_revision = isoformat_utc()
        self.store.save_computer(record)
        return record

    def takeover(self, bot: Bot) -> TakeoverResult:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if record.state != "running" or not record.provider_ref:
            raise ComputerError("computer is not running")
        if record.scope == "team" and record.execution_bot_id and record.execution_bot_id != bot.id:
            if self.store.has_active_run(record.execution_bot_id):
                name = self.store.busy_bot_name(record, bot.id) or "another bot"
                raise ComputerBusy(name)
        if record.control_holder == "user" and record.control_lease_id and record.control_lease_expires_at:
            expires = record.control_lease_expires_at
            return TakeoverResult(lease_id=record.control_lease_id, expires_at=expires)
        lease_id = new_id("lease")
        expires_at = isoformat_utc(datetime.now(timezone.utc) + self._takeover_ttl())
        record.control_holder = "user"
        record.control_lease_id = lease_id
        record.control_lease_expires_at = expires_at
        record.control_bot_id = bot.id
        record = self._touch(record)
        self.store.save_computer(record)
        return TakeoverResult(lease_id=lease_id, expires_at=expires_at)

    def release(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        if record.provider_ref and record.control_lease_id:
            try:
                self.client.screen_mode(record.provider_ref, False, record.control_lease_id)
            except Exception:
                log.exception("failed to drop control screen")
        record.control_holder = "bot"
        record.control_lease_id = None
        record.control_lease_expires_at = None
        record.control_bot_id = None
        self.store.save_computer(record)
        return self.status(bot)

    def heartbeat(self, bot: Bot) -> ComputerStatus:
        record = self.store.get_computer_for_bot(bot)
        if record.state == "running":
            record = self._touch(record)
            self.store.save_computer(record)
        return self.status(bot)

    def screen_url(self, bot: Bot) -> ScreenUrlResult:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if record.state not in {"running", "booting"} or not record.provider_ref:
            return ScreenUrlResult(url=None)
        if record.kind == "fake" or self.settings.sandbox_provider == "fake":
            return ScreenUrlResult(url=None)
        interactive = self._user_has_control(record)
        control_ready = False
        try:
            box = self.client.screen_mode(
                record.provider_ref,
                interactive,
                record.control_lease_id if interactive else None,
            )
            control_ready = interactive and bool(box.control_port) and box.ok
        except Exception:
            log.exception("screen-mode failed")
            try:
                box = self.client.inspect(record.provider_ref)
            except Exception:
                log.exception("inspect fallback failed, rebooting container")
                try:
                    record.provider_ref = None
                    record.state = "stopped"
                    self.store.save_computer(record)
                    self.boot(bot)
                    record = self.store.get_computer_for_bot(bot)
                    if record.provider_ref:
                        box = self.client.inspect(record.provider_ref)
                    else:
                        raise ComputerUnavailable("screen unavailable")
                except ComputerUnavailable:
                    raise
                except Exception as err:
                    raise ComputerUnavailable("screen unavailable") from err
        port = box.control_port if control_ready else box.view_port
        if not port:
            raise ComputerUnavailable("screen unavailable")
        secret = self.settings.agent_http_token
        url = mint_novnc_url(secret, "127.0.0.1", int(port), interactive=control_ready)
        record = self._touch(record)
        self.store.save_computer(record)
        return ScreenUrlResult(url=url)

    def list_files(self, bot: Bot, path: str = "/", hidden: bool = False) -> ComputerFileList:
        home, target = self._home_target(bot, path)
        display = self._rel_home(home, target)
        if target.is_file():
            return ComputerFileList(path=display, entries=[self._file_entry(home, target)])
        if not target.is_dir():
            raise ComputerError("path not found")
        children = sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        entries = [
            self._file_entry(home, child)
            for child in children
            if hidden or not child.name.startswith(".")
        ]
        return ComputerFileList(path=display, entries=entries)

    def read_file(self, bot: Bot, path: str) -> ComputerFileContent:
        target = self._home_target(bot, path)[1]
        if not target.is_file():
            raise ComputerError("file not found")
        data = target.read_bytes()
        if len(data) > MAX_HOME_READ_BYTES:
            raise ComputerError("file too large")
        return ComputerFileContent(path=self._display_path(path), content=data.decode("utf-8", errors="replace"))

    def file_for_download(self, bot: Bot, path: str) -> tuple[Path, str, str]:
        target = self._home_target(bot, path)[1]
        if not target.is_file():
            raise ComputerError("file not found")
        size = target.stat().st_size
        if size > MAX_HOME_DOWNLOAD_BYTES:
            raise ComputerError("file too large")
        mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return target, target.name, mime

    def _home_target(self, bot: Bot, rel: str) -> tuple[Path, Path]:
        record = self.store.get_computer_for_bot(bot)
        home = self.home_path(record).resolve()
        cleaned = (rel or "").replace("\\", "/").strip()
        if cleaned in {"", ".", "/"}:
            return home, home
        parts = [part for part in cleaned.lstrip("/").split("/") if part and part != "."]
        if not parts or any(part == ".." for part in parts):
            raise ComputerError("invalid path")
        target = home.joinpath(*parts).resolve()
        try:
            target.relative_to(home)
        except ValueError as err:
            raise ComputerError("invalid path") from err
        return home, target

    def _rel_home(self, home: Path, target: Path) -> str:
        if target == home:
            return ""
        return str(target.relative_to(home)).replace("\\", "/")

    def _display_path(self, rel: str) -> str:
        cleaned = (rel or "").replace("\\", "/").strip().lstrip("/")
        return "" if cleaned in {".", "/"} else cleaned

    def _file_entry(self, home: Path, item: Path) -> ComputerFileEntry:
        kind = "dir" if item.is_dir() else "file"
        size = item.stat().st_size if item.is_file() else 0
        return ComputerFileEntry(
            path=self._rel_home(home, item),
            name=item.name,
            kind=kind,
            size=size,
        )

    def send_input(self, bot: Bot, kind: str, payload: dict[str, Any]) -> None:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if not self._user_has_control(record) or not record.provider_ref:
            raise ComputerError("take control first")
        self.client.send_input(record.provider_ref, kind, payload)
        record = self._touch(record)
        self.store.save_computer(record)

    def ensure_running(self, bot: Bot) -> ComputerRecord:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if record.state != "running" or not record.provider_ref or not self._box_alive(record.provider_ref):
            self.boot(bot)
            record = self.store.get_computer_for_bot(bot)
        record = self._touch(record)
        self.store.save_computer(record)
        return record

    def observe(self, bot: Bot) -> dict[str, Any]:
        record = self.ensure_running(bot)
        return self.client.observe(record.provider_ref)

    def act(self, bot: Bot, actions: list[dict[str, Any]]) -> dict[str, Any]:
        record = self.ensure_running(bot)
        return self.client.act(record.provider_ref, actions)

    def exec_command(self, bot: Bot, command: str) -> dict[str, Any]:
        record = self.ensure_running(bot)
        return self.client.execute(record.provider_ref, command)

    def open_path(self, bot: Bot, path: str) -> dict[str, Any]:
        record = self.ensure_running(bot)
        return self.client.act(record.provider_ref, [{"kind": "open", "path": path}])

    def launch_app(self, bot: Bot, name: str, uri: str | None = None) -> dict[str, Any]:
        record = self.ensure_running(bot)
        action: dict[str, Any] = {"kind": "launch", "name": name}
        if uri:
            action["uri"] = uri
        return self.client.act(record.provider_ref, [action])

    def close_app(self, bot: Bot, name: str) -> dict[str, Any]:
        record = self.store.get_computer_for_bot(bot)
        record = self._expire_lease(record)
        if record.state != "running" or not record.provider_ref:
            return {"ok": True, "closed": name, "state": record.state}
        record = self._touch(record)
        self.store.save_computer(record)
        return self.client.act(record.provider_ref, [{"kind": "close", "name": name}])

    def switch_mode(self, bot: Bot, mode: str) -> Bot:
        if self.store.has_active_run(bot.id):
            raise ComputerBusy(bot.name)
        updated = self.store.update_bot(bot.id, computer_mode=mode)
        if updated is None:
            raise ComputerError("bot not found")
        self.store.ensure_computer(updated)
        return self.store.get_bot(updated.id) or updated

    def _box_alive(self, provider_ref: str) -> bool:
        try:
            box = self.client.inspect(provider_ref)
        except Exception:
            return False
        if not box.running:
            return False
        if self.settings.sandbox_provider == "fake" or (box.id or "").startswith("fake-"):
            return True
        return bool(box.view_port or box.control_port)

    def _touch(self, record: ComputerRecord) -> ComputerRecord:
        record.sleep_at = isoformat_utc(datetime.now(timezone.utc) + self._idle_ttl())
        return record

    def _takeover_ttl(self) -> timedelta:
        return timedelta(seconds=max(60, int(self.settings.computer_takeover_ttl_seconds)))

    def _idle_ttl(self) -> timedelta:
        return timedelta(seconds=max(60, int(self.settings.computer_idle_seconds)))

    def _user_has_control(self, record: ComputerRecord) -> bool:
        if record.control_holder != "user" or not record.control_lease_id or not record.control_lease_expires_at:
            return False
        expires = datetime.fromisoformat(record.control_lease_expires_at.replace("Z", "+00:00"))
        return expires > datetime.now(timezone.utc)

    def _expire_lease(self, record: ComputerRecord) -> ComputerRecord:
        if record.control_holder != "user" or not record.control_lease_expires_at:
            return record
        expires = datetime.fromisoformat(record.control_lease_expires_at.replace("Z", "+00:00"))
        if expires > datetime.now(timezone.utc):
            return record
        if record.provider_ref and record.control_lease_id:
            try:
                self.client.screen_mode(record.provider_ref, False, record.control_lease_id)
            except Exception:
                log.exception("failed to expire control screen")
        record.control_holder = "none"
        record.control_lease_id = None
        record.control_lease_expires_at = None
        record.control_bot_id = None
        return self.store.save_computer(record)
