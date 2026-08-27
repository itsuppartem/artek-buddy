from __future__ import annotations

from typing import Any

from artek_buddy.apps import CONNECT_REDIRECT, MAX_APP_ROWS


class AppsToolsMixin:
    def _apps_broker(self) -> tuple[Any, str | None]:
        store = getattr(self.runtime, "store", None)
        settings = getattr(self.runtime, "settings", None)
        if store is None or settings is None:
            return None, "store is not available"
        key = store.raw_connection_key()
        if not key:
            return None, "paste a key in Plugins"
        from artek_buddy.runtime.factory import runtime_kind

        if runtime_kind(settings) == "scripted":
            from artek_buddy.connections.broker import fake_broker

            return fake_broker(), None
        from artek_buddy.connections.http import HttpBroker

        return HttpBroker(key), None

    def _apps_say(self, args: dict[str, Any], bound_bot_id: str | None, text: str) -> None:
        self._append_bot_blocks(
            args,
            bound_bot_id,
            [{"kind": "text", "text": text}],
            mark_sent=False,
        )

    def _app_card(
        self,
        args: dict[str, Any],
        bound_bot_id: str | None,
        name: str,
        text: str,
        url: str | None = None,
    ) -> None:
        block: dict[str, Any] = {"kind": "plugin", "name": name, "text": text}
        if url:
            block["url"] = url
        self._append_bot_blocks(args, bound_bot_id, [block], mark_sent=False)

    def _exec_list_apps(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        broker, missing = self._apps_broker()
        if broker is None:
            self._apps_say(args, bound_bot_id, missing or "paste a key in Plugins")
            return {"ok": False, "error": missing or "paste a key in Plugins"}
        store = self.runtime.store
        query = str(args.get("q") or args.get("query") or "").strip() or None
        try:
            rows = broker.catalog(query, store.connected_slugs())[:MAX_APP_ROWS]
        except Exception as exc:
            from artek_buddy.connections.broker import hide_secret

            secret = store.raw_connection_key() or ""
            err = hide_secret(str(exc), secret)
            self._apps_say(args, bound_bot_id, err)
            return {"ok": False, "error": err}
        items = [
            {
                "slug": row.slug,
                "name": row.name,
                "connected": row.connected,
                "no_auth": row.no_auth,
            }
            for row in rows
        ]
        return {"ok": True, "items": items}

    def _exec_connect_app(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        broker, missing = self._apps_broker()
        if broker is None:
            self._apps_say(args, bound_bot_id, missing or "paste a key in Plugins")
            return {"ok": False, "error": missing or "paste a key in Plugins"}
        store = self.runtime.store
        slug = str(args.get("slug") or args.get("app") or args.get("name") or "").strip().lower()
        if not slug:
            self._apps_say(args, bound_bot_id, "app not found")
            return {"ok": False, "error": "app not found"}
        existing = store.active_for_provider(slug)
        if existing is not None and existing.status == "connected":
            self._app_card(
                args,
                bound_bot_id,
                existing.display_name,
                "Already connected. Use it this turn if the tools are loaded, or next turn.",
            )
            return {
                "ok": True,
                "already": True,
                "slug": slug,
                "status": "connected",
            }
        if existing is not None:
            self._app_card(
                args,
                bound_bot_id,
                existing.display_name,
                "Sign-in is already started. Open Plugins and Finish if needed.",
            )
            return {
                "ok": True,
                "already": True,
                "slug": slug,
                "status": existing.status,
            }
        try:
            started = broker.begin(slug, CONNECT_REDIRECT)
        except KeyError:
            self._apps_say(args, bound_bot_id, "app not found")
            return {"ok": False, "error": "app not found"}
        except Exception as exc:
            from artek_buddy.connections.broker import hide_secret

            secret = store.raw_connection_key() or ""
            err = hide_secret(str(exc), secret)
            self._apps_say(args, bound_bot_id, err)
            return {"ok": False, "error": err}
        connection = store.insert_connection(
            provider=slug,
            display_name=started.display_name,
            status=started.status,
            capabilities=started.capabilities,
            no_auth=started.no_auth,
            remote_id=started.remote_id,
        )
        if connection.status == "connected":
            self._app_card(
                args,
                bound_bot_id,
                connection.display_name,
                "Connected. That app's tools are on the next turn.",
            )
        else:
            self._app_card(
                args,
                bound_bot_id,
                connection.display_name,
                "Open this link to sign in, then Finish in Plugins if the row stays pending.",
                url=started.authorization_url,
            )
        return {
            "ok": True,
            "slug": slug,
            "status": connection.status,
            "id": connection.id,
            "url": started.authorization_url,
        }
