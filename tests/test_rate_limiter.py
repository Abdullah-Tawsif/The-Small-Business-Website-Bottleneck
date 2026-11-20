import asyncio
import hashlib
import os
import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

import middleware.rate_limiter as rate_limiter_module
from config.settings import Settings
from middleware.rate_limiter import InMemoryRateLimitMiddleware, RateLimitMiddleware


def make_request(client_ip, app=None, path="/resource"):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "client": (client_ip, 12345),
            "app": app or SimpleNamespace(state=SimpleNamespace()),
        }
    )


def test_rate_limiter_blocks_requests_after_client_limit(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_requests=1,
            rate_limit_window_seconds=60,
        ),
    )
    limiter = InMemoryRateLimitMiddleware(lambda *_args: None)
    call_count = 0

    async def call_next(_request):
        nonlocal call_count
        call_count += 1
        return Response("ok")

    async def run():
        first = await limiter.dispatch(make_request("192.0.2.10"), call_next)
        second = await limiter.dispatch(make_request("192.0.2.10"), call_next)
        other_client = await limiter.dispatch(make_request("192.0.2.11"), call_next)
        return first, second, other_client

    first, second, other_client = asyncio.run(run())

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) > 0
    assert other_client.status_code == 200
    assert call_count == 2


class SharedTestRedis:
    """Small shared fake for deterministic middleware contract tests."""

    def __init__(self):
        self.counts = {}

    async def eval(self, _script, _key_count, key, ttl):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key], ttl

    async def time(self):
        import time

        return int(time.time()), 0


def test_redis_limiter_shares_counts_between_middleware_instances(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_requests=1,
            rate_limit_window_seconds=60,
            rate_limit_redis_url="redis://local.test/0",
        ),
    )
    shared_store = SharedTestRedis()
    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=shared_store))
    first_worker = RateLimitMiddleware(lambda *_args: None)
    second_worker = RateLimitMiddleware(lambda *_args: None)

    async def call_next(_request):
        return Response("ok")

    async def run():
        first = await first_worker.dispatch(make_request("192.0.2.20", app), call_next)
        second = await second_worker.dispatch(make_request("192.0.2.20", app), call_next)
        return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200
    assert second.status_code == 429


def test_health_and_readiness_bypass_rate_limit_store(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            rate_limit_requests=1,
            rate_limit_window_seconds=60,
            rate_limit_redis_url="redis://unavailable.invalid/0",
        ),
    )
    limiter = RateLimitMiddleware(lambda *_args: None)
    reached = []

    async def call_next(request):
        reached.append(request.url.path)
        return Response("ok")

    async def run():
        health = await limiter.dispatch(
            make_request("192.0.2.30", path="/health"), call_next
        )
        readiness = await limiter.dispatch(
            make_request("192.0.2.30", path="/ready"), call_next
        )
        return health, readiness

    health, readiness = asyncio.run(run())
    assert health.status_code == 200
    assert readiness.status_code == 200
    assert reached == ["/health", "/ready"]


def test_production_rate_limiter_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            rate_limit_requests=2,
            rate_limit_redis_url="redis://unavailable.invalid/0",
        ),
    )
    limiter = RateLimitMiddleware(lambda *_args: None)
    call_count = 0

    async def call_next(_request):
        nonlocal call_count
        call_count += 1
        return Response("ok")

    response = asyncio.run(
        limiter.dispatch(make_request("192.0.2.21"), call_next)
    )
    assert response.status_code == 503
    assert call_count == 0


@pytest.mark.skipif(
    not os.getenv("AGENCYFORGE_TEST_REDIS_URL"),
    reason="requires an explicitly disposable Redis test service",
)
@pytest.mark.anyio
async def test_real_redis_shares_limits_between_application_instances(monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from redis.asyncio import Redis
    from sqlalchemy.engine import make_url

    redis_url = os.environ["AGENCYFORGE_TEST_REDIS_URL"]
    target = make_url(redis_url)
    if target.host not in {"127.0.0.1", "localhost", "::1"} or target.database != "15":
        pytest.skip(
            "Redis integration requires an explicitly disposable localhost database 15."
        )
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_requests=1,
            rate_limit_window_seconds=60,
            rate_limit_redis_url=redis_url,
        ),
    )

    first_redis = Redis.from_url(redis_url, decode_responses=True)
    second_redis = Redis.from_url(redis_url, decode_responses=True)
    # The limiter keys include a hash of the client address. Give this test a
    # unique synthetic address so it can clean up only its own Redis keys.
    client_ip = f"agencyforge-test-{uuid.uuid4().hex}"
    client_key = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    test_key_pattern = f"agencyforge:rate-limit:v1:{client_key}:*"
    try:
        applications = []
        for redis_client in (first_redis, second_redis):
            app = FastAPI()
            app.state.rate_limit_redis = redis_client
            app.add_middleware(RateLimitMiddleware)

            @app.get("/limited")
            async def limited_resource():
                return {"status": "ok"}

            applications.append(app)

        assert applications[0] is not applications[1]
        first_transport = ASGITransport(app=applications[0], client=(client_ip, 12345))
        second_transport = ASGITransport(app=applications[1], client=(client_ip, 12345))
        async with (
            AsyncClient(transport=first_transport, base_url="http://test") as first,
            AsyncClient(transport=second_transport, base_url="http://test") as second,
        ):
            first_response = await first.get("/limited")
            second_response = await second.get("/limited")
        assert first_response.status_code == 200
        assert second_response.status_code == 429
    finally:
        # Never flush the Redis database: delete only keys created for this
        # test's unique synthetic client identity.
        test_keys = [key async for key in first_redis.scan_iter(match=test_key_pattern)]
        if test_keys:
            await first_redis.delete(*test_keys)
        await first_redis.aclose()
        await second_redis.aclose()


@pytest.fixture
def anyio_backend():
    return "asyncio"
