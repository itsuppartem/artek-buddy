from __future__ import annotations

import ipaddress
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from artek_buddy.books import MAX_BODY, BookError

FIXTURE_SKILL_MD = (
    "---\n"
    "name: Invoice\n"
    "description: When I say invoice\n"
    "---\n"
    "\n"
    "Open the invoice site and download the PDF.\n"
)

_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
_FETCH_TIMEOUT_S = 8.0
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class SkillFixture:
    def __init__(self, url: str, server: ThreadingHTTPServer) -> None:
        self.url = url
        self._server = server

    def close(self) -> None:
        self._server.shutdown()


def start_skill_fixture() -> SkillFixture:
    body = FIXTURE_SKILL_MD.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/SKILL.md"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/markdown; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, name="artek-book-fixture", daemon=True)
    thread.start()
    port = int(server.server_address[1])
    return SkillFixture(f"http://127.0.0.1:{port}/SKILL.md", server)


def blocked_fetch_url(url: str) -> str | None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return "url must be http or https"
    if parsed.username or parsed.password:
        return "that skill URL is not a public site"
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return "that skill URL is not a public site"
    if not host:
        return "url must be http or https"
    if port is not None and not (1 <= port <= 65535):
        return "that skill URL is not a public site"
    if host in _BLOCKED_HOSTS or host.endswith(".localhost"):
        return "that skill URL is not a public site"
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and _ip_blocked(literal):
        return "that skill URL is not a public site"
    return None


def fetch_skill_document(url: str, *, allow_url: str | None = None) -> str:
    target = (url or "").strip()
    if not target:
        raise BookError("url cannot be empty")
    allowed = (allow_url or "").strip()
    if not allowed or _canon(target) != _canon(allowed):
        reason = blocked_fetch_url(target) or _resolved_private(target)
        if reason:
            raise BookError(reason)
    return _http_get(target)


def _resolved_private(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        return "url must be http or https"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return "that skill URL is not a public site"
    try:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return "that skill URL is not a public site"
    for item in records:
        sockaddr = item[4]
        try:
            found = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            return "that skill URL is not a public site"
        if _ip_blocked(found):
            return "that skill URL is not a public site"
    return None


def _canon(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    path = parsed.path or "/"
    return f"{parsed.scheme}://{host}:{port}{path}"


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = ip.ipv4_mapped if isinstance(ip, ipaddress.IPv6Address) else None
    if mapped is not None:
        return _ip_blocked(mapped)
    if ip.is_loopback or ip.is_private or ip.is_link_local:
        return True
    if ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return True
    return ip.version == 4 and ip in _CGNAT


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        raise BookError("that skill URL redirected")


def _http_get(url: str) -> str:
    request = Request(
        url,
        method="GET",
        headers={"User-Agent": "artek-buddy-book", "Accept": "text/markdown, text/plain, */*"},
    )
    opener = build_opener(ProxyHandler({}), _RejectRedirect)
    try:
        with opener.open(request, timeout=_FETCH_TIMEOUT_S) as resp:
            raw = resp.read(MAX_BODY + 1)
    except BookError:
        raise
    except HTTPError as err:
        raise BookError(f"could not fetch that skill ({err.code})") from err
    except (URLError, TimeoutError, OSError) as err:
        raise BookError("could not fetch that skill") from err
    if len(raw) > MAX_BODY:
        raise BookError(f"body is longer than {MAX_BODY} characters")
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        raise BookError("body cannot be empty")
    return text
