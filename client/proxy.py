from __future__ import annotations

import secrets
import subprocess  # noqa: F401
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from notifications import _desktop_dismiss as _desktop_dismiss  # noqa: F401
from notifications import _desktop_notify as _desktop_notify  # noqa: F401
from pairing import _config_dir as _config_dir  # noqa: F401
from pairing import _log
from proxy_common import (
    LOCAL_JSON_MAX,
    WEB_ROOTS,
    choose_save_path,
    local_rpc_origin_allowed,
    proxy_host_allowed,
    proxy_origin_allowed,
    save_path_chooser,
    web_root,
)
from proxy_rpc import LocalRpcMixin
from proxy_static import StaticMixin
from proxy_upstream import UpstreamMixin
from ssh_mux import owner_exec_environment as owner_exec_environment  # noqa: F401

__all__ = [
    "Handler",
    "LOCAL_JSON_MAX",
    "WEB_ROOTS",
    "choose_save_path",
    "local_rpc_origin_allowed",
    "proxy_host_allowed",
    "proxy_origin_allowed",
    "save_path_chooser",
    "serve",
    "web_root",
]


class Handler(LocalRpcMixin, UpstreamMixin, StaticMixin, BaseHTTPRequestHandler):
    server_version = "artek-buddy"

    def log_message(self, fmt: str, *args) -> None:
        _log("client: " + (fmt % args))

    def _accept_browser(self) -> bool:
        port = int(self.server.server_address[1])
        if proxy_origin_allowed(
            self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site"), port
        ):
            return True
        self.send_error(403, "cross-origin request blocked")
        return False

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def do_GET(self) -> None:
        path = self._route()
        if path == "/local/status":
            if not self._accept_local(mutating=False):
                return
            self._local_status()
            return
        if path == "/health" or path.startswith("/v1/") or path.startswith("/novnc/"):
            if (
                path.startswith("/novnc/")
                and (self.headers.get("Upgrade") or "").lower() == "websocket"
            ):
                self._proxy_ws()
                return
            self._proxy()
            return
        self._static()

    def do_POST(self) -> None:
        path = self._route()
        if path.startswith("/local/"):
            if not self._accept_local(mutating=True):
                return
        if path == "/local/pair":
            self._local_pair()
            return
        if path == "/local/unpair":
            self._local_unpair()
            return
        if path == "/local/notify":
            self._local_notify()
            return
        if path == "/local/notify-dismiss":
            self._local_notify_dismiss()
            return
        if path == "/local/owner-read":
            self._local_owner_read()
            return
        if path == "/local/owner-write":
            self._local_owner_write()
            return
        if path == "/local/owner-list":
            self._local_owner_list()
            return
        if path == "/local/owner-exec":
            self._local_owner_exec()
            return
        if path == "/local/save-artifact":
            self._local_save_artifact()
            return
        if path == "/local/save-home-file":
            self._local_save_home_file()
            return
        if path == "/local/attach-files":
            self._local_attach_files()
            return
        if path.startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_PUT(self) -> None:
        if self._route().startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        if self._route().startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        if self._route().startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        if not self._accept_browser():
            return
        self.send_response(204)
        self.send_header(
            "Access-Control-Allow-Headers",
            "Authorization, Content-Type, Accept, X-Artek-Local-Nonce",
        )
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()


def serve(url: str, token: str, port: int = 0) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.upstream = url
    httpd.token = token
    httpd.web_root = web_root()
    httpd.local_nonce = secrets.token_urlsafe(32)
    return httpd
