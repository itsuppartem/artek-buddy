#!/usr/bin/env python3
"""Desktop shell: local proxy + web UI. Credentials stay on this machine."""

from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

_CLIENT_DIR = Path(__file__).resolve().parent
if str(_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLIENT_DIR))

from notifications import _desktop_dismiss as _desktop_dismiss
from notifications import _desktop_notify as _desktop_notify
from owner_paths import _owner_path_status as _owner_path_status
from owner_paths import inspect_owner_path as inspect_owner_path
from owner_paths import resolve_owner_path as resolve_owner_path
from owner_paths import unique_download_dest as unique_download_dest
from pairing import _load_token, _load_url, _log
from pairing import pairing_url_allowed as pairing_url_allowed
from proxy import local_rpc_origin_allowed as local_rpc_origin_allowed
from proxy import proxy_host_allowed as proxy_host_allowed
from proxy import proxy_origin_allowed as proxy_origin_allowed
from proxy import serve
from window import open_window
from window_chrome import bundled_icon_path as bundled_icon_path
from window_chrome import identify_desktop_app as identify_desktop_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="artek-buddy")
    parser.add_argument("--serve", action="store_true", help="proxy only; do not open a window")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    url = _load_url()
    token = _load_token()
    _log("start token_ok=%s url_scheme=%s" % (bool(token), urlsplit(url).scheme or "none"))
    try:
        httpd = serve(url, token, args.port)
    except Exception:
        import traceback

        _log("proxy failed:\n" + traceback.format_exc())
        sys.exit(2)
    host, port = httpd.server_address[:2]
    local = f"http://{host}:{port}/"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    if args.serve:
        print(local)
        try:
            thread.join()
        except KeyboardInterrupt:
            httpd.shutdown()
        return
    if open_window(local):
        httpd.shutdown()
        return
    _log("no webkit window; opening the system browser")
    webbrowser.open(local)
    try:
        thread.join()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
