import asyncio

import pytest

from middleware.request_size_limit import RequestSizeLimitMiddleware


def run_asgi(middleware, scope, incoming_messages):
    messages = iter(incoming_messages)
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def run():
        await middleware(scope, receive, send)

    asyncio.run(run())
    return sent


def scope(headers=(), scope_type="http"):
    return {"type": scope_type, "method": "POST", "path": "/submit", "headers": list(headers)}


def test_request_within_limit_reaches_application_with_complete_body():
    received = []

    async def app(_scope, receive, send):
        received.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    result = run_asgi(
        RequestSizeLimitMiddleware(app, max_body_bytes=8),
        scope([(b"content-length", b"4")]),
        [{"type": "http.request", "body": b"data", "more_body": False}],
    )

    assert received == [{"type": "http.request", "body": b"data", "more_body": False}]
    assert result[0]["status"] == 200


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"9")],
        [],  # Chunked or otherwise unknown body length.
    ],
)
def test_oversized_request_body_is_rejected(headers):
    async def app(*_args):
        pytest.fail("Oversized request reached the application")

    incoming = (
        []
        if headers
        else [
            {"type": "http.request", "body": b"1234", "more_body": True},
            {"type": "http.request", "body": b"56789", "more_body": False},
        ]
    )
    sent = run_asgi(
        RequestSizeLimitMiddleware(app, max_body_bytes=8),
        scope(headers),
        incoming,
    )

    assert sent[0]["status"] == 413
    assert b"Request body too large." in sent[1]["body"]


def test_invalid_content_length_is_rejected():
    async def app(*_args):
        pytest.fail("Invalid Content-Length reached the application")

    sent = run_asgi(
        RequestSizeLimitMiddleware(app, max_body_bytes=8),
        scope([(b"content-length", b"not-a-number")]),
        [],
    )

    assert sent[0]["status"] == 400


def test_non_http_scope_is_passed_through():
    received_scope = []

    async def app(current_scope, _receive, _send):
        received_scope.append(current_scope)

    websocket_scope = {"type": "websocket", "path": "/socket"}
    run_asgi(
        RequestSizeLimitMiddleware(app, max_body_bytes=8),
        websocket_scope,
        [],
    )

    assert received_scope == [websocket_scope]


def test_rate_limiter_wraps_body_buffering_middleware():
    from main import app
    from middleware.rate_limiter import RateLimitMiddleware

    middleware_types = [entry.cls for entry in app.user_middleware]

    assert middleware_types.index(RateLimitMiddleware) < middleware_types.index(
        RequestSizeLimitMiddleware
    )
