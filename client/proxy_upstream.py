from __future__ import annotations

import http.client
import select
import socket
import ssl
from urllib.parse import urlsplit

from pairing import _log


class UpstreamMixin:
    def _proxy(self) -> None:
        if not self._accept_browser():
            return
        upstream = urlsplit(self.server.upstream)  # type: ignore[attr-defined]
        token = self.server.token  # type: ignore[attr-defined]
        path = self.path
        body = b""
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            body = self.rfile.read(length)
        headers = {
            "Accept": self.headers.get("Accept", "application/json"),
            "Authorization": f"Bearer {token}",
            "Connection": "close",
        }
        if body:
            headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
        if upstream.scheme == "https":
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                upstream.hostname or "127.0.0.1",
                upstream.port or 443,
                timeout=600,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(
                upstream.hostname or "127.0.0.1",
                upstream.port or 80,
                timeout=600,
            )
        try:
            conn.request(self.command, path, body=body or None, headers=headers)
            resp = conn.getresponse()
            body_expected = self.command != "HEAD" and resp.status not in {204, 304}
            content_length = (
                resp.getheader("Content-Length") if body_expected and not resp.chunked else None
            )
            chunked = body_expected and content_length is None
            self.send_response(resp.status)
            connection_headers = {
                item.strip().lower()
                for value in (resp.headers.get_all("Connection") or [])
                for item in value.split(",")
            }
            skip = {
                "connection",
                "content-length",
                "keep-alive",
                "proxy-authenticate",
                "proxy-authorization",
                "te",
                "trailer",
                "transfer-encoding",
                "upgrade",
                *connection_headers,
            }
            for key, value in resp.getheaders():
                if key.lower() in skip:
                    continue
                self.send_header(key, value)
            if content_length is not None:
                self.send_header("Content-Length", content_length)
            elif chunked:
                self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if body_expected:
                while True:
                    chunk = resp.read1(16384) if hasattr(resp, "read1") else resp.read(16384)
                    if not chunk:
                        break
                    if chunked:
                        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                        self.wfile.write(chunk)
                        self.wfile.write(b"\r\n")
                    else:
                        self.wfile.write(chunk)
                    self.wfile.flush()
            if chunked:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return
        finally:
            conn.close()

    def _proxy_ws(self) -> None:
        if not self._accept_browser():
            return
        upstream = urlsplit(self.server.upstream)  # type: ignore[attr-defined]
        token = self.server.token  # type: ignore[attr-defined]
        host = upstream.hostname or "127.0.0.1"
        port = upstream.port or (443 if upstream.scheme == "https" else 80)
        try:
            raw = socket.create_connection((host, port), timeout=30)
            sock: socket.socket = raw
            if upstream.scheme == "https":
                ctx = ssl.create_default_context()
                ctx.minimum_version = ssl.TLSVersion.TLSv1_2
                sock = ctx.wrap_socket(raw, server_hostname=host)
        except OSError:
            self.send_error(502, "host unreachable")
            return
        host_header = host if port in {80, 443} else f"{host}:{port}"
        lines = [
            f"{self.command} {self.path} HTTP/1.1",
            f"Host: {host_header}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Authorization: Bearer {token}",
        ]
        for key in (
            "Sec-WebSocket-Key",
            "Sec-WebSocket-Version",
            "Sec-WebSocket-Protocol",
            "Sec-WebSocket-Extensions",
            "Origin",
        ):
            value = self.headers.get(key)
            if value:
                lines.append(f"{key}: {value}")
        try:
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1"))
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            header, rest = buf.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in buf else (buf, b"")
            first = header.split(b"\r\n", 1)[0]
            parts = first.split(None, 2)
            status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 502
            # WebSocket clients require HTTP/1.1 101. BaseHTTPRequestHandler
            # defaults to HTTP/1.0, which leaves noVNC on a black canvas.
            out = [f"HTTP/1.1 {status} Switching Protocols"]
            skip = {b"transfer-encoding", b"connection", b"keep-alive", b"content-length"}
            have_upgrade = False
            for line in header.split(b"\r\n")[1:]:
                if b":" not in line:
                    continue
                key, value = line.split(b":", 1)
                if key.lower() in skip:
                    continue
                if key.lower() == b"upgrade":
                    have_upgrade = True
                out.append(f"{key.decode('latin1')}: {value.decode('latin1').strip()}")
            out.append("Connection: upgrade")
            if not have_upgrade:
                out.append("Upgrade: websocket")
            client = self.connection
            client.sendall(("\r\n".join(out) + "\r\n\r\n").encode("iso-8859-1") + rest)
            self.close_connection = True
            _log("novnc ws status=%s" % status)
            while True:
                readable, _, _ = select.select([client, sock], [], [], 60)
                if not readable:
                    continue
                if client in readable:
                    data = client.recv(16384)
                    if not data:
                        break
                    sock.sendall(data)
                if sock in readable:
                    data = sock.recv(16384)
                    if not data:
                        break
                    client.sendall(data)
        except (BrokenPipeError, OSError):
            return
        finally:
            try:
                sock.close()
            except OSError:
                pass
