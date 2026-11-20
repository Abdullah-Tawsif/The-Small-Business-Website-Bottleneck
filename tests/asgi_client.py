"""Synchronous test adapter over HTTPX's in-process ASGI transport.

Starlette's synchronous TestClient starts an AnyIO portal on a background
thread. Some restricted runners do not wake that thread's selector when a
cross-thread callback is queued. This adapter keeps each ASGI request on the
calling thread's event loop while preserving the small synchronous interface
used by the API tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.dependencies import utils as dependency_utils
from fastapi import routing as fastapi_routing


class SyncASGIClient:
    """Small sync client that dispatches each request through ASGITransport."""

    def __init__(self, app: FastAPI, base_url: str = "http://testserver"):
        self.app = app
        self.base_url = base_url
        self.cookies = httpx.Cookies()
        self._patchers = []

    def __enter__(self) -> SyncASGIClient:
        from config.settings import validate_runtime_settings
        from database.database import verify_schema

        async def run_inline(func, *args, **kwargs):
            return func(*args, **kwargs)

        @asynccontextmanager
        async def contextmanager_inline(cm):
            value = cm.__enter__()
            try:
                yield value
            except BaseException as exc:
                if not cm.__exit__(type(exc), exc, exc.__traceback__):
                    raise
            else:
                cm.__exit__(None, None, None)

        # This restricted runner cannot wake its selector from AnyIO worker
        # threads. Keep sync route/dependency execution inline for these tests;
        # the real ASGI stack, request handling and middleware remain intact.
        self._patchers = [
            patch.object(fastapi_routing, "run_in_threadpool", run_inline),
            patch.object(dependency_utils, "run_in_threadpool", run_inline),
            patch.object(
                dependency_utils,
                "contextmanager_in_threadpool",
                contextmanager_inline,
            ),
        ]
        for patcher in self._patchers:
            patcher.start()
        try:
            validate_runtime_settings()
            verify_schema()
        except BaseException:
            self.__exit__()
            raise
        return self

    def __exit__(self, *_exc_info) -> None:
        for patcher in reversed(self._patchers):
            patcher.stop()
        return None

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json: Any = None,
        follow_redirects: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        async def dispatch() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url=self.base_url,
                cookies=self.cookies,
                follow_redirects=follow_redirects,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    **kwargs,
                )
                self.cookies.update(client.cookies)
                return response

        return asyncio.run(dispatch())

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)
