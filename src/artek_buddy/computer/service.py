from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from artek_buddy.computer.client import FakeSupervisorClient, SupervisorClient
from artek_buddy.computer.models import ComputerRecord
from artek_buddy.computer.screen import mint_novnc_url
from artek_buddy.config import Settings
from artek_buddy.contracts.domain import (
    Bot,
    ComputerFileContent,
    ComputerFileList,
    ComputerStatus,
    ScreenUrlResult,
    TakeoverResult,
)
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc, new_id

log = logging.getLogger("artek_buddy")

EXEC_TTL = timedelta(minutes=5)


class ComputerBusy(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class ComputerError(Exception):
    pass


class ComputerService:
    def __init__(self, store: HistoryStore, settings: Settings, client: Any | None = None) -> None:
        self.store = store
        self.settings = settings
        if client is not None:
            self.client = client
        elif settings.sandbox_provider == "fake":
            self.client = FakeSupervisorClient()
        else:
            token = settings.sandbox_supervisor_token or settings.agent_http_token
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
        if record.state == "running" and record.provider_ref:
            record = self._touch(record)
            self.store.save_computer(record)
            return self.status(bot)
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
                    self.boot(bot)
                    record = self.store.get_computer_for_bot(bot)
                    if record.provider_ref:
                        box = self.client.inspect(record.provider_ref)
                    else:
                        return ScreenUrlResult(url=None)
                except Exception:
                    return ScreenUrlResult(url=None)
        port = box.control_port if control_ready else box.view_port
        if not port:
            return ScreenUrlResult(url=None)
        secret = self.settings.agent_http_token
        url = mint_novnc_url(secret, "127.0.0.1", int(port), interactive=control_ready)
        record = self._touch(record)
        self.store.save_computer(record)
        return ScreenUrlResult(url=url)

    def list_files(self, bot: Bot, path: str = "/") -> ComputerFileList:
        record = self.store.get_computer_for_bot(bot)
        if record.state == "running" and record.provider_ref:
            payload = self.client.list_files(record.provider_ref, path)
            entries = [
                {"path": str(item.get("path")), "kind": item.get("kind") or "file", "size": int(item.get("size") or 0)}
                for item in payload.get("entries") or []
            ]
            return ComputerFileList(path=path, entries=entries)
        home = self.home_path(record)
        target = (home / path.lstrip("/")).resolve()
        try:
            target.relative_to(home.resolve())
        except ValueError as err:
            raise ComputerError("invalid path") from err
        entries = []
        if target.is_dir():
            for child in sorted(target.iterdir()):
                entries.append(
                    {
                        "path": child.name,
                        "kind": "dir" if child.is_dir() else "file",
                        "size": child.stat().st_size if child.is_file() else 0,
                    }
                )
        return ComputerFileList(path=path, entries=entries)

    def read_file(self, bot: Bot, path: str) -> ComputerFileContent:
        record = self.store.get_computer_for_bot(bot)
        home = self.home_path(record)
        target = (home / path.lstrip("/")).resolve()
        try:
            target.relative_to(home.resolve())
        except ValueError as err:
            raise ComputerError("invalid path") from err
        if not target.is_file():
            raise ComputerError("file not found")
        data = target.read_bytes()
        if len(data) > 2 * 1024 * 1024:
            raise ComputerError("file too large")
        return ComputerFileContent(path=path, content=data.decode("utf-8", errors="replace"))

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
        if record.state != "running" or not record.provider_ref:
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
