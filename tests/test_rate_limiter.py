import asyncio
import hashlib
import os
import time
import uuid
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import Response

import middleware.rate_limiter as rate_limiter_module
from config.settings import Settings
from middleware.rate_limiter import InMemoryRateLimitMiddleware, RateLimitMiddleware


def make_request(client_ip, app=None, path="/resource", headers=None, method="GET"):
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": headers or [],
            "client": (client_ip, 12345),
            "app": app or SimpleNamespace(state=SimpleNamespace()),
        }
    )


def test_auth_limit_is_per_source_ip_across_account_identifiers(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            auth_rate_limit_requests=1,
            rate_limit_window_seconds=60,
            rate_limit_redis_url="redis://local.test/0",
        ),
    )
    store = SharedTestRedis()
    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=store))
    limiter = RateLimitMiddleware(lambda *_args: None)

    async def call_next(_request):
        return Response("ok")

    async def run():
        first = await limiter.dispatch(
            make_request(
                "192.0.2.40", app, "/api/auth/login",
                [(b"x-account", b"one")], method="POST",
            ),
            call_next,
        )
        second = await limiter.dispatch(
            make_request(
                "192.0.2.40", app, "/api/auth/login",
                [(b"x-account", b"two")], method="POST",
            ),
            call_next,
        )
        return first, second

    first, second = asyncio.run(run())
    assert first.status_code == 200
    assert second.status_code == 429


def test_rate_limiter_blocks_requests_after_client_limit(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_requests=1,
            api_rate_limit_requests=1,
            rate_limit_window_seconds=4,
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

    async def eval(self, _script, _key_count, key, window, retention):
        now = int(time.time())
        counter_key = (key, now // int(window))
        self.counts[counter_key] = self.counts.get(counter_key, 0) + 1
        return self.counts[counter_key], int(window) - now % int(window)

    async def time(self):
        raise AssertionError("The rate limiter must read time inside its atomic script.")


def test_redis_limiter_shares_counts_between_middleware_instances(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            rate_limit_requests=1,
            api_rate_limit_requests=1,
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


def test_trusted_proxy_uses_client_chain_and_untrusted_forwarding_is_ignored():
    trusted_request = make_request(
        "10.0.0.8",
        path="/resource",
        headers=[(b"x-forwarded-for", b"198.51.100.20, 10.0.0.7")],
    )
    untrusted_request = make_request(
        "192.0.2.8",
        path="/resource",
        headers=[(b"x-forwarded-for", b"203.0.113.99")],
    )
    assert RateLimitMiddleware._client_ip(
        trusted_request, "10.0.0.0/8"
    ) == "198.51.100.20"
    assert RateLimitMiddleware._client_ip(
        untrusted_request, "10.0.0.0/8"
    ) == "192.0.2.8"


def test_trusted_proxy_uses_nearest_untrusted_address_across_multiple_hops():
    request = make_request(
        "10.0.0.8",
        headers=[(
            b"x-forwarded-for",
            b"203.0.113.44, 198.51.100.22, 10.0.0.7",
        )],
    )
    assert RateLimitMiddleware._client_ip(request, "10.0.0.0/8") == "198.51.100.22"


def test_malformed_forwarding_data_falls_back_to_peer():
    request = make_request(
        "10.0.0.8",
        headers=[(b"x-forwarded-for", b"198.51.100.22, definitely-not-an-ip")],
    )
    assert RateLimitMiddleware._client_ip(request, "10.0.0.0/8") == "10.0.0.8"


def test_untrusted_peer_cannot_change_rate_identity_with_forwarded_header():
    first = make_request(
        "192.0.2.50",
        headers=[(b"x-forwarded-for", b"198.51.100.1")],
    )
    second = make_request(
        "192.0.2.50",
        headers=[(b"x-forwarded-for", b"198.51.100.2")],
    )
    assert RateLimitMiddleware._client_ip(first, "10.0.0.0/8") == "192.0.2.50"
    assert RateLimitMiddleware._client_ip(second, "10.0.0.0/8") == "192.0.2.50"


def test_endpoint_categories_separate_public_writes_from_admin_lead_operations():
    settings = Settings(_env_file=None)
    assert RateLimitMiddleware._policy("/api/auth/login", settings)[0] == "authentication"
    assert RateLimitMiddleware._policy("/api/leads/", settings, "POST")[0] == "public-write"
    assert RateLimitMiddleware._policy("/api/leads/", settings, "GET")[0] == "administration"
    assert RateLimitMiddleware._policy("/api/leads/7/status", settings, "PATCH")[0] == "administration"
    assert RateLimitMiddleware._policy("/api/scoping/", settings, "POST")[0] == "ai"
    assert RateLimitMiddleware._policy("/static/css/site.css", settings)[0] == "static"


def test_admin_budgets_are_partitioned_by_authenticated_user(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            admin_rate_limit_requests=1,
            rate_limit_window_seconds=60,
            rate_limit_redis_url="redis://local.test/0",
        ),
    )
    monkeypatch.setattr(
        rate_limiter_module,
        "decode_access_token",
        lambda token: {"sub": token.removeprefix("user-")},
    )
    store = SharedTestRedis()
    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=store))
    limiter = RateLimitMiddleware(lambda *_args: None)

    async def call_next(_request):
        return Response("ok")

    async def run():
        users = ["user-101", "user-202"]
        first = [
            await limiter.dispatch(
                make_request(
                    "10.0.0.1",
                    app,
                    "/api/admin/users",
                    [(b"authorization", f"Bearer {token}".encode())],
                ),
                call_next,
            )
            for token in users
        ]
        second = [
            await limiter.dispatch(
                make_request(
                    "10.0.0.1",
                    app,
                    "/api/admin/users",
                    [(b"authorization", f"Bearer {token}".encode())],
                ),
                call_next,
            )
            for token in users
        ]
        return first, second

    first, second = asyncio.run(run())
    assert [response.status_code for response in first] == [200, 200]
    assert [response.status_code for response in second] == [429, 429]


def test_health_bypasses_limiter_but_readiness_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            rate_limit_requests=1,
            api_rate_limit_requests=1,
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
    assert readiness.status_code == 503
    assert reached == ["/health"]


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
            api_rate_limit_requests=1,
            rate_limit_window_seconds=4,
            rate_limit_redis_url=redis_url,
        ),
    )

    first_redis = Redis.from_url(redis_url, decode_responses=True)
    second_redis = Redis.from_url(redis_url, decode_responses=True)
    # The limiter keys include a hash of the client address. Give this test a
    # unique synthetic address so it can clean up only its own Redis keys.
    client_ip = f"agencyforge-test-{uuid.uuid4().hex}"
    client_key = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    test_key_pattern = f"agencyforge:rate-limit:v3:{{{client_key}}}:application-api:*"
    concurrent_ip = f"agencyforge-test-{uuid.uuid4().hex}"
    concurrent_key = hashlib.sha256(concurrent_ip.encode("utf-8")).hexdigest()
    concurrent_pattern = (
        f"agencyforge:rate-limit:v3:{{{concurrent_key}}}:application-api:*"
    )
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
            retry_after = int(second_response.headers["Retry-After"])
            keys = [key async for key in first_redis.scan_iter(match=test_key_pattern)]
            assert len(keys) == 1
            retained_ttl = await first_redis.ttl(keys[0])
            assert retry_after <= 4
            assert retained_ttl > retry_after
            await asyncio.sleep(retry_after + 0.15)
            boundary_response = await second.get("/limited")
            assert await first_redis.hlen(keys[0]) == 1
            boundary_ttl = await first_redis.ttl(keys[0])
            assert boundary_ttl > 0
            await asyncio.sleep(boundary_ttl + 0.15)
            assert await first_redis.exists(keys[0]) == 0

            concurrent_transport_a = ASGITransport(
                app=applications[0], client=(concurrent_ip, 12345)
            )
            concurrent_transport_b = ASGITransport(
                app=applications[1], client=(concurrent_ip, 12345)
            )
            async with (
                AsyncClient(transport=concurrent_transport_a, base_url="http://test") as concurrent_a,
                AsyncClient(transport=concurrent_transport_b, base_url="http://test") as concurrent_b,
            ):
                concurrent_results = await asyncio.gather(
                    concurrent_a.get("/limited"),
                    concurrent_b.get("/limited"),
                )
        assert first_response.status_code == 200
        assert second_response.status_code == 429
        assert boundary_response.status_code == 200
        assert sorted(response.status_code for response in concurrent_results) == [200, 429]
    finally:
        # Never flush the Redis database: delete only keys created for this
        # test's unique synthetic client identity.
        test_keys = [key async for key in first_redis.scan_iter(match=test_key_pattern)]
        test_keys.extend(
            [key async for key in first_redis.scan_iter(match=concurrent_pattern)]
        )
        if test_keys:
            await first_redis.delete(*test_keys)
        await first_redis.aclose()
        await second_redis.aclose()


@pytest.mark.skipif(
    not os.getenv("AGENCYFORGE_TEST_REDIS_URL"),
    reason="requires an explicitly disposable Redis test service",
)
@pytest.mark.anyio
async def test_real_redis_rate_limiter_fails_closed_during_outage_and_recovers(
    monkeypatch,
):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from redis.asyncio import Redis
    from sqlalchemy.engine import make_url

    redis_url = os.environ["AGENCYFORGE_TEST_REDIS_URL"]
    target = make_url(redis_url)
    if target.host not in {"127.0.0.1", "localhost", "::1"} or target.database != "15":
        pytest.skip("Redis integration requires disposable localhost Redis DB 15.")

    monkeypatch.setattr(
        rate_limiter_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://agency:secret@localhost/agencyforge",
            jwt_secret_key="real-redis-rate-limit-test-secret-material",
            api_rate_limit_requests=10,
            rate_limit_window_seconds=4,
            rate_limit_redis_url=redis_url,
        ),
    )

    control = Redis.from_url(redis_url, decode_responses=True)
    limited = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=0.1,
    )
    client_ip = f"agencyforge-test-outage-{uuid.uuid4().hex}"
    client_key = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
    pattern = f"agencyforge:rate-limit:v3:{{{client_key}}}:application-api:*"
    app = FastAPI()
    app.state.rate_limit_redis = limited
    app.add_middleware(RateLimitMiddleware)

    @app.get("/limited")
    async def limited_resource():
        return {"status": "ok"}

    try:
        await control.ping()
        await control.execute_command("CLIENT", "PAUSE", 500, "ALL")
        async with AsyncClient(
            transport=ASGITransport(app=app, client=(client_ip, 12345)),
            base_url="http://test",
        ) as client:
            unavailable = await client.get("/limited")
            assert unavailable.status_code == 503
            await asyncio.sleep(0.6)
            recovered = await client.get("/limited")
            assert recovered.status_code == 200
    finally:
        keys = [key async for key in control.scan_iter(match=pattern)]
        if keys:
            await control.delete(*keys)
        await limited.aclose()
        await control.aclose()


@pytest.fixture
def anyio_backend():
    return "asyncio"
