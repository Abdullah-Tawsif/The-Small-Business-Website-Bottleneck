"""Bound HTTP request bodies before handing requests to application routes."""

import json
from collections.abc import Awaitable, Callable
from typing import Any

from config.settings import get_settings

ASGIMessage = dict[str, Any]
Receive = Callable[[], Awaitable[ASGIMessage]]
Send = Callable[[ASGIMessage], Awaitable[None]]


class RequestSizeLimitMiddleware:
    """Reject HTTP request bodies larger than the configured byte limit."""

    def __init__(self, app, max_body_bytes: int | None = None):
        self.app = app
        self.max_body_bytes = (
            max_body_bytes
            if max_body_bytes is not None
            else get_settings().max_request_body_bytes
        )
        if self.max_body_bytes <= 0:
            raise ValueError("max_body_bytes must be positive")

    async def __call__(self, scope: dict[str, Any], receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        raw_content_length = headers.get(b"content-length")
        if raw_content_length is not None:
            try:
                content_length = int(raw_content_length)
            except ValueError:
                await self._reject(send, 400, "Invalid Content-Length header.")
                return
            if content_length < 0:
                await self._reject(send, 400, "Invalid Content-Length header.")
                return
            if content_length > self.max_body_bytes:
                await self._reject(send, 413, "Request body too large.")
                return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue

            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_body_bytes:
                await self._reject(send, 413, "Request body too large.")
                return

            body.extend(chunk)
            more_body = message.get("more_body", False)

        body_message = {"type": "http.request", "body": bytes(body), "more_body": False}
        body_sent = False

        async def replay_body() -> ASGIMessage:
            nonlocal body_sent
            if not body_sent:
                body_sent = True
                return body_message
            return await receive()

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _reject(send: Send, status_code: int, detail: str) -> None:
        content = json.dumps({"detail": detail}).encode("utf-8")
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(content)).encode("ascii")),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": content,
            "more_body": False,
        })
