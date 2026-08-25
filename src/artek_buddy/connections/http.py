from __future__ import annotations

from typing import Any

import httpx

from artek_buddy.connections.broker import (
    OWNER_USER_ID,
    BeginRemote,
    FakeApp,
    filter_catalog,
    hide_secret,
    validate_redirect,
)
from artek_buddy.contracts.domain import ConnectionCatalogItem
from artek_buddy.runtime.tools.specs import ToolSpec

_BASE = "https://backend.composio.dev/api/v3.1"
_TIMEOUT = 20.0
_TOOL_CAP = 8


class HttpBroker:
    def __init__(self, key: str) -> None:
        self._key = (key or "").strip()

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self._key, "Accept": "application/json"}

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with httpx.Client(timeout=_TIMEOUT) as client:
            return client.request(method, f"{_BASE}{path}", headers=self._headers(), **kwargs)

    def catalog(self, q: str | None, connected: set[str]) -> list[ConnectionCatalogItem]:
        params: dict[str, str] = {"limit": "50"}
        needle = (q or "").strip()
        if needle:
            params["search"] = needle
        response = self._request("GET", "/toolkits", params=params)
        if response.status_code >= 400:
            raise RuntimeError(hide_secret("could not load the catalog", self._key))
        payload = response.json()
        rows = payload.get("items") or payload.get("toolkits") or payload.get("data") or []
        items: list[ConnectionCatalogItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            slug = str(row.get("slug") or row.get("toolkit_slug") or "").strip().lower()
            name = str(row.get("name") or slug).strip()
            if not slug or not name:
                continue
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            logo = row.get("logo") or meta.get("logo")
            items.append(
                ConnectionCatalogItem(
                    slug=slug,
                    name=name,
                    logo=str(logo) if logo else None,
                    connected=slug in connected,
                    no_auth=bool(row.get("no_auth")),
                )
            )
        return filter_catalog(items, q)

    def describe(self, slug: str) -> FakeApp | None:
        return None

    def _auth_config_id(self, slug: str) -> str:
        listed = self._request("GET", "/auth_configs", params={"toolkit_slug": slug})
        if listed.status_code < 400:
            payload = listed.json()
            rows = payload.get("items") or payload.get("auth_configs") or []
            for row in rows:
                if isinstance(row, dict) and row.get("id"):
                    return str(row["id"])
        created = self._request("POST", "/auth_configs", json={"toolkit": {"slug": slug}})
        if created.status_code >= 400:
            raise RuntimeError(hide_secret("could not start that connection", self._key))
        body = created.json()
        auth_id = body.get("id") or (body.get("auth_config") or {}).get("id")
        if not auth_id:
            raise RuntimeError(hide_secret("could not start that connection", self._key))
        return str(auth_id)

    def begin(self, slug: str, redirect_url: str) -> BeginRemote:
        callback = validate_redirect(redirect_url)
        toolkit = self._request("GET", f"/toolkits/{slug}")
        no_auth = False
        display = slug
        if toolkit.status_code < 400:
            body = toolkit.json()
            no_auth = bool(body.get("no_auth"))
            display = str(body.get("name") or slug)
        if no_auth:
            return BeginRemote(
                status="connected",
                remote_id=f"none_{slug}",
                authorization_url=None,
                capabilities=self._tool_names(slug),
                display_name=display,
                no_auth=True,
            )
        auth_id = self._auth_config_id(slug)
        linked = self._request(
            "POST",
            "/connected_accounts/link",
            json={
                "auth_config_id": auth_id,
                "user_id": OWNER_USER_ID,
                "callback_url": callback,
            },
        )
        if linked.status_code >= 400:
            raise RuntimeError(hide_secret("could not start that connection", self._key))
        payload = linked.json()
        remote_id = str(payload.get("id") or payload.get("connected_account_id") or "")
        url = payload.get("redirect_url") or payload.get("redirectUrl")
        if not remote_id:
            raise RuntimeError(hide_secret("could not start that connection", self._key))
        return BeginRemote(
            status="pending",
            remote_id=remote_id,
            authorization_url=str(url) if url else None,
            capabilities=[],
            display_name=display,
            no_auth=False,
        )

    def complete(self, remote_id: str) -> str:
        if remote_id.startswith("none_"):
            return "connected"
        response = self._request("GET", f"/connected_accounts/{remote_id}")
        if response.status_code >= 400:
            raise RuntimeError(hide_secret("could not finish that connection", self._key))
        status = str(response.json().get("status") or "").upper()
        if status in {"ACTIVE", "CONNECTED"}:
            return "connected"
        return "pending"

    def revoke(self, remote_id: str) -> None:
        if remote_id.startswith("none_"):
            return
        self._request("POST", f"/connected_accounts/{remote_id}/revoke")

    def _tool_names(self, slug: str) -> list[str]:
        return [spec.name for spec in self.tool_specs([slug])]

    def tool_specs(self, slugs: list[str]) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for slug in slugs:
            response = self._request(
                "GET",
                "/tools",
                params={"toolkit_slug": slug, "limit": str(_TOOL_CAP)},
            )
            if response.status_code >= 400:
                continue
            payload = response.json()
            rows = payload.get("items") or payload.get("tools") or []
            for row in rows[:_TOOL_CAP]:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("slug") or row.get("name") or "").strip()
                if not name:
                    continue
                description = str(row.get("description") or f"Call {name} on the connected app.")
                schema = (
                    row.get("input_parameters")
                    or row.get("input_schema")
                    or {
                        "type": "object",
                        "properties": {},
                    }
                )
                if not isinstance(schema, dict):
                    schema = {"type": "object", "properties": {}}
                specs.append(ToolSpec(name=name, description=description, input_schema=schema))
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
        _ = provider, key
        body: dict[str, Any] = {
            "arguments": args or {},
            "user_id": OWNER_USER_ID,
        }
        if remote_id and not remote_id.startswith("none_"):
            body["connected_account_id"] = remote_id
        response = self._request("POST", f"/tools/execute/{name}", json=body)
        if response.status_code >= 400:
            return {"ok": False, "error": hide_secret("that app call failed", self._key)}
        payload = response.json()
        text = payload.get("data") or payload.get("result") or payload
        return {"ok": True, "text": str(text)[:8000], "announce": True}
