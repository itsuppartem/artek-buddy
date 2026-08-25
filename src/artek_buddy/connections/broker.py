from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit

from artek_buddy.contracts.domain import ConnectionCatalogItem
from artek_buddy.runtime.tools.specs import ToolSpec

DOCS_TEXT = "The notes app has one page: Subotica."
MAX_KEY_CHARS = 512
MAX_SEARCH_CHARS = 80
OWNER_USER_ID = "usr_owner"


@dataclass(frozen=True)
class FakeApp:
    slug: str
    name: str
    no_auth: bool
    tool: str
    text: str
    description: str


FAKE_APPS: tuple[FakeApp, ...] = (
    FakeApp("mail", "Mail", False, "mail_inbox", "Inbox is empty.", "Read the connected mailbox."),
    FakeApp("chat", "Chat", False, "chat_unread", "No unread chats.", "Read unread chat threads."),
    FakeApp("issues", "Issues", False, "issues_list", "No open issues.", "List open issues."),
    FakeApp(
        "calendar",
        "Calendar",
        False,
        "calendar_today",
        "Nothing today.",
        "Read today's calendar.",
    ),
    FakeApp("docs", "Docs", True, "docs_read", DOCS_TEXT, "Read the connected docs page."),
)
APPS_BY_SLUG = {item.slug: item for item in FAKE_APPS}


@dataclass
class BeginRemote:
    status: str
    remote_id: str
    authorization_url: str | None
    capabilities: list[str]
    display_name: str
    no_auth: bool


def filter_catalog(
    items: list[ConnectionCatalogItem], q: str | None
) -> list[ConnectionCatalogItem]:
    needle = (q or "").strip().lower()[:MAX_SEARCH_CHARS]
    if not needle:
        return items
    return [item for item in items if needle in item.slug.lower() or needle in item.name.lower()]


def validate_redirect(url: str) -> str:
    raw = (url or "").strip()
    parts = urlsplit(raw)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.netloc
        or parts.username
        or parts.password
    ):
        raise ValueError("redirect url is invalid")
    return raw


def hide_secret(message: str, key: str) -> str:
    text = (message or "").strip() or "that app is unavailable"
    secret = (key or "").strip()
    if secret and secret in text:
        return text.replace(secret, "[redacted]")
    return text


class Broker(Protocol):
    def catalog(self, q: str | None, connected: set[str]) -> list[ConnectionCatalogItem]: ...
    def describe(self, slug: str) -> FakeApp | None: ...
    def begin(self, slug: str, redirect_url: str) -> BeginRemote: ...
    def complete(self, remote_id: str) -> str: ...
    def revoke(self, remote_id: str) -> None: ...
    def tool_specs(self, slugs: list[str]) -> list[ToolSpec]: ...
    def execute(
        self,
        name: str,
        args: dict[str, Any],
        *,
        provider: str,
        remote_id: str | None,
        key: str,
    ) -> dict[str, Any]: ...


@dataclass
class FakeBroker:
    _remote: dict[str, str] = field(default_factory=dict)
    _active: set[str] = field(default_factory=set)

    def catalog(self, q: str | None, connected: set[str]) -> list[ConnectionCatalogItem]:
        items = [
            ConnectionCatalogItem(
                slug=app.slug,
                name=app.name,
                logo=None,
                connected=app.slug in connected,
                no_auth=app.no_auth,
            )
            for app in FAKE_APPS
        ]
        return filter_catalog(items, q)

    def describe(self, slug: str) -> FakeApp | None:
        return APPS_BY_SLUG.get((slug or "").strip().lower())

    def hydrate(self, slugs: list[str]) -> None:
        for slug in slugs:
            app = self.describe(slug)
            if app is None:
                continue
            remote_id = f"fake_{app.slug}"
            self._remote[remote_id] = app.slug
            self._active.add(remote_id)

    def begin(self, slug: str, redirect_url: str) -> BeginRemote:
        app = self.describe(slug)
        if app is None:
            raise KeyError(slug)
        validate_redirect(redirect_url)
        remote_id = f"fake_{app.slug}"
        if app.no_auth:
            self._remote[remote_id] = app.slug
            self._active.add(remote_id)
            return BeginRemote(
                status="connected",
                remote_id=remote_id,
                authorization_url=None,
                capabilities=[app.tool],
                display_name=app.name,
                no_auth=True,
            )
        self._remote[remote_id] = app.slug
        return BeginRemote(
            status="pending",
            remote_id=remote_id,
            authorization_url=f"https://example.test/authorize?app={app.slug}",
            capabilities=[],
            display_name=app.name,
            no_auth=False,
        )

    def complete(self, remote_id: str) -> str:
        slug = self._remote.get(remote_id)
        if not slug:
            raise KeyError(remote_id)
        self._active.add(remote_id)
        return "connected"

    def revoke(self, remote_id: str) -> None:
        self._active.discard(remote_id)

    def tool_specs(self, slugs: list[str]) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for slug in slugs:
            app = self.describe(slug)
            if app is None:
                continue
            if f"fake_{app.slug}" not in self._active:
                continue
            specs.append(
                ToolSpec(
                    name=app.tool,
                    description=app.description,
                    input_schema={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                )
            )
        return specs

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        *,
        provider: str,
        remote_id: str | None,
        key: str,
    ) -> dict[str, Any]:
        _ = args, key
        app = self.describe(provider)
        if app is None or app.tool != name:
            return {"ok": False, "error": "app is not connected"}
        if not remote_id or remote_id not in self._active:
            return {"ok": False, "error": "app is not connected"}
        return {"ok": True, "text": app.text, "announce": True}


_FAKE = FakeBroker()


def fake_broker() -> FakeBroker:
    return _FAKE


def reset_fake_broker() -> None:
    _FAKE._remote.clear()
    _FAKE._active.clear()
