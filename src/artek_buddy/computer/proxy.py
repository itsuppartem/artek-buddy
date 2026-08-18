from __future__ import annotations

import asyncio
import logging
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException, Request, WebSocket
from fastapi.responses import Response

from artek_buddy.computer.screen import resolve_novnc_target

log = logging.getLogger("artek_buddy")

HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def signed_target(url: str, secret: str) -> Any:
    target = resolve_novnc_target(url, secret)
    if target is None:
        raise HTTPException(status_code=403, detail="invalid screen url")
    return target


def fetch_novnc(url: str, method: str) -> Response:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            data = resp.read()
            content_type = resp.headers.get("Content-Type") or "application/octet-stream"
            return Response(content=data, media_type=content_type, status_code=resp.status)
    except urllib.error.HTTPError as err:
        return Response(content=err.read(), status_code=err.code)
    except OSError as err:
        raise HTTPException(status_code=502, detail="screen unreachable") from err


async def proxy_novnc_http(request: Request, secret: str) -> Response:
    full = request.url.path
    if request.url.query:
        full = f"{full}?{request.url.query}"
    target = signed_target(full, secret)
    url = f"http://{target.hostname}:{target.port}{target.path}"
    return await asyncio.to_thread(fetch_novnc, url, request.method)


async def proxy_novnc_ws(websocket: WebSocket, secret: str) -> None:
    full = websocket.url.path
    if websocket.url.query:
        full = f"{full}?{websocket.url.query}"
    target = resolve_novnc_target(full, secret)
    if target is None:
        await websocket.close(code=4403)
        return
    upstream_url = f"ws://{target.hostname}:{target.port}{target.path}"
    try:
        import websockets
    except ImportError as err:
        log.exception("websockets missing")
        await websocket.close(code=1011)
        raise HTTPException(status_code=500, detail="screen proxy unavailable") from err
    try:
        async with websockets.connect(upstream_url, ping_interval=None, open_timeout=10) as upstream:
            await websocket.accept()

            async def down() -> None:
                try:
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        data = message.get("bytes")
                        text = message.get("text")
                        if data is not None:
                            await upstream.send(data)
                        elif text is not None:
                            await upstream.send(text)
                except Exception:
                    pass

            async def up() -> None:
                try:
                    async for message in upstream:
                        if isinstance(message, bytes):
                            await websocket.send_bytes(message)
                        else:
                            await websocket.send_text(str(message))
                except Exception:
                    pass

            await asyncio.gather(down(), up())
    except Exception:
        log.exception("novnc websocket failed")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
