from __future__ import annotations

import socket
import struct
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection, HTTPResponse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

import proxy  # noqa: E402
import proxy_rpc  # noqa: E402

FIRST_EVENT = b"id: progress-1\ndata: Still working: first step\n\n"


class QuietHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return


@contextmanager
def running_server(handler: type[BaseHTTPRequestHandler]) -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def running_proxy(upstream: ThreadingHTTPServer) -> Iterator[tuple[ThreadingHTTPServer, int]]:
    port = int(upstream.server_address[1])
    with TemporaryDirectory() as directory:
        Path(directory, "index.html").write_text("<!doctype html>", encoding="utf-8")
        original_web_root = proxy.web_root
        proxy.web_root = lambda: Path(directory)
        try:
            server = proxy.serve(f"http://127.0.0.1:{port}", "device-token", 0)
        finally:
            proxy.web_root = original_web_root
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server, int(server.server_address[1])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def request_headers(port: int) -> dict[str, str]:
    return {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "Accept": "text/event-stream",
    }


def test_oversized_body_drain_stops_after_first_byte_over_limit() -> None:
    stream = BytesIO(b"x" * 20)
    handler = SimpleNamespace(rfile=stream, close_connection=False)

    proxy_rpc.LocalRpcMixin._drain_oversized_body(handler, length=20, limit=8)

    assert stream.tell() == 9
    assert stream.read() == b"x" * 11
    assert handler.close_connection is True


def test_unpair_consumes_body_before_next_request_on_same_connection() -> None:
    with TemporaryDirectory() as directory:
        original_config_dir = proxy._config_dir
        proxy._config_dir = lambda: Path(directory)
        try:
            with running_server(QuietHandler) as upstream:
                with running_proxy(upstream) as (server, port):
                    server.token = "device-token"  # type: ignore[attr-defined]
                    conn = HTTPConnection("127.0.0.1", port, timeout=5)
                    try:
                        conn.request(
                            "POST",
                            "/local/unpair",
                            body=b"{}",
                            headers={
                                "Host": f"127.0.0.1:{port}",
                                "Origin": f"http://127.0.0.1:{port}",
                                "Content-Type": "application/json",
                                "X-Artek-Local-Nonce": server.local_nonce,  # type: ignore[attr-defined]
                            },
                        )
                        unpair = conn.getresponse()
                        unpair.read()
                        assert unpair.status == 200

                        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{port}"})
                        page = conn.getresponse()
                        body = page.read()
                        assert page.status == 200
                        assert body == b"<!doctype html>"
                    finally:
                        conn.close()
        finally:
            proxy._config_dir = original_config_dir


def test_first_sse_frame_is_chunked_before_upstream_closes() -> None:
    first_sent = threading.Event()
    release_upstream = threading.Event()
    upstream_closed = threading.Event()

    class StreamingUpstream(QuietHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(FIRST_EVENT)
            self.wfile.flush()
            first_sent.set()
            release_upstream.wait(timeout=5)
            upstream_closed.set()

    with running_server(StreamingUpstream) as upstream:
        with running_proxy(upstream) as (_server, port):
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                conn.request("GET", "/v1/events", headers=request_headers(port))
                response = conn.getresponse()
                assert first_sent.wait(timeout=5)
                assert response.read(len(FIRST_EVENT)) == FIRST_EVENT
                assert not upstream_closed.is_set()
                assert response.version == 11
                assert response.getheader("Transfer-Encoding") == "chunked"
                assert response.getheader("Content-Length") is None
            finally:
                release_upstream.set()
                conn.close()


def test_finite_get_and_post_preserve_content_length_and_body() -> None:
    seen: list[tuple[str, str, bytes, str | None]] = []

    class FiniteUpstream(QuietHandler):
        def _respond(self, payload: bytes, request_body: bytes = b"") -> None:
            seen.append(
                (
                    self.command,
                    self.path,
                    request_body,
                    self.headers.get("Authorization"),
                )
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            self._respond(b'{"kind":"get"}')

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            self._respond(b'{"kind":"post"}', self.rfile.read(length))

    with running_server(FiniteUpstream) as upstream:
        with running_proxy(upstream) as (_server, port):
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            try:
                conn.request("GET", "/v1/finite", headers=request_headers(port))
                get_response = conn.getresponse()
                get_body = get_response.read()

                post_body = b'{"message":"hello"}'
                conn.request(
                    "POST",
                    "/v1/finite",
                    body=post_body,
                    headers={
                        **request_headers(port),
                        "Content-Type": "application/json",
                    },
                )
                post_response = conn.getresponse()
                returned_post_body = post_response.read()
            finally:
                conn.close()

    assert get_response.version == 11
    assert get_response.getheader("Content-Length") == str(len(get_body))
    assert get_response.getheader("Transfer-Encoding") is None
    assert get_body == b'{"kind":"get"}'
    assert post_response.version == 11
    assert post_response.getheader("Content-Length") == str(len(returned_post_body))
    assert post_response.getheader("Transfer-Encoding") is None
    assert returned_post_body == b'{"kind":"post"}'
    assert seen == [
        ("GET", "/v1/finite", b"", "Bearer device-token"),
        ("POST", "/v1/finite", b'{"message":"hello"}', "Bearer device-token"),
    ]


def test_stream_disconnect_closes_the_upstream_response() -> None:
    release_upstream = threading.Event()
    proxy_disconnected = threading.Event()

    class StreamingUpstream(QuietHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(FIRST_EVENT)
            self.wfile.flush()
            release_upstream.wait(timeout=5)
            try:
                self.wfile.write(b"x" * (4 * 1024 * 1024))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                proxy_disconnected.set()

    with running_server(StreamingUpstream) as upstream:
        with running_proxy(upstream) as (_server, port):
            client = socket.create_connection(("127.0.0.1", port), timeout=5)
            response: HTTPResponse | None = None
            try:
                request = (
                    "GET /v1/events HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{port}\r\n"
                    f"Origin: http://127.0.0.1:{port}\r\n"
                    "Accept: text/event-stream\r\n"
                    "\r\n"
                )
                client.sendall(request.encode("ascii"))
                response = HTTPResponse(client)
                response.begin()
                assert response.version == 11
                assert response.read(len(FIRST_EVENT)) == FIRST_EVENT
                response.close()
                client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                client.close()
                release_upstream.set()
                assert proxy_disconnected.wait(timeout=5)
            finally:
                release_upstream.set()
                if response is not None:
                    response.close()
                client.close()
