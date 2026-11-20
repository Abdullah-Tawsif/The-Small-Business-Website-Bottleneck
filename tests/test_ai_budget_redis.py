"""Real Redis coverage for shared, atomic AI request budgets."""

import asyncio
import os
import uuid
from types import SimpleNamespace

import pytest
from redis.asyncio import Redis
from sqlalchemy.engine import make_url

from routes.scoping import _reserve_ai_budget, _run_budget_script


REDIS_URL = os.getenv("AGENCYFORGE_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not REDIS_URL,
    reason="requires the disposable Redis CI service",
)


@pytest.mark.anyio
async def test_shared_ai_account_session_and_global_budgets_are_atomic(monkeypatch):
    from fastapi import HTTPException
    target = make_url(REDIS_URL)
    if target.host not in {"127.0.0.1", "localhost", "::1"} or target.database != "15":
        pytest.skip("AI budget integration requires disposable localhost Redis DB 15.")
    namespace = f"agencyforge-test-{uuid.uuid4().hex}"
    first = Redis.from_url(REDIS_URL, decode_responses=True)
    second = Redis.from_url(REDIS_URL, decode_responses=True)
    identity = uuid.uuid4().hex
    session = uuid.uuid4().hex
    try:
        results = await asyncio.gather(
            _run_budget_script(first, identity, session, 1, 10, 100, namespace),
            _run_budget_script(second, identity, session, 1, 10, 100, namespace),
        )
        assert sorted(result[0] for result in results) == [False, True]
        new_session_result = await _run_budget_script(
            second, identity, uuid.uuid4().hex, 1, 10, 100, namespace
        )
        assert new_session_result[0] is False

        from config.settings import Settings
        import config.settings as settings_module

        application_namespace = f"{namespace}:applications"
        monkeypatch.setattr(
            settings_module,
            "get_settings",
            lambda: Settings(
                _env_file=None,
                environment="development",
                database_url="sqlite:////tmp/agencyforge-ai-budget-test.sqlite",
                jwt_secret_key="real-redis-ai-budget-test-secret-material",
                rate_limit_redis_url=REDIS_URL,
                ai_account_daily_limit=1,
                ai_session_daily_limit=5,
                ai_global_daily_limit=10,
                ai_budget_namespace=application_namespace,
            ),
        )
        request_a = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            app=SimpleNamespace(state=SimpleNamespace(rate_limit_redis=first)),
        )
        request_b = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            app=SimpleNamespace(state=SimpleNamespace(rate_limit_redis=second)),
        )

        async def reserve_from_application(request):
            try:
                await _reserve_ai_budget(request, 700_321, None)
            except HTTPException as error:
                if error.status_code != 429:
                    raise
                return False
            return True

        application_results = await asyncio.gather(
            reserve_from_application(request_a),
            reserve_from_application(request_b),
        )
        assert sorted(application_results) == [False, True]

        session_first = await _run_budget_script(
            first, uuid.uuid4().hex, "one-session", 10, 1, 100, namespace
        )
        session_exhausted = await _run_budget_script(
            second, uuid.uuid4().hex, "one-session", 10, 1, 100, namespace
        )
        assert session_first[0] is True
        assert session_exhausted[0] is False
        assert session_exhausted[1] > 0

        global_namespace = f"{namespace}:global"
        global_first = await _run_budget_script(
            first, "global-user-a", "global-session-a", 10, 10, 1, global_namespace
        )
        global_exhausted = await _run_budget_script(
            second,
            "global-user-b",
            "global-session-b",
            10,
            10,
            1,
            global_namespace,
        )
        assert global_first[0] is True
        assert global_exhausted[0] is False

        for budget_namespace in (namespace, global_namespace):
            pattern = f"{budget_namespace}:ai-budget:{{shared}}:*"
            keys = [key async for key in first.scan_iter(match=pattern)]
            assert keys
            assert all([await first.ttl(key) > 0 for key in keys])
    finally:
        patterns = (
            f"{namespace}:ai-budget:{{shared}}:*",
            f"{namespace}:global:ai-budget:{{shared}}:*",
            f"{namespace}:applications:ai-budget:{{shared}}:*",
        )
        keys = []
        for pattern in patterns:
            keys.extend([key async for key in first.scan_iter(match=pattern)])
        if keys:
            await first.delete(*keys)
        await first.aclose()
        await second.aclose()


@pytest.mark.anyio
async def test_guest_budgets_share_trusted_proxy_identity_across_redis_clients(
    monkeypatch,
):
    from fastapi import HTTPException
    from starlette.requests import Request

    target = make_url(REDIS_URL)
    if target.host not in {"127.0.0.1", "localhost", "::1"} or target.database != "15":
        pytest.skip("AI budget integration requires disposable localhost Redis DB 15.")

    from config.settings import Settings
    import config.settings as settings_module

    namespace = f"agencyforge-test-proxy-{uuid.uuid4().hex}"
    first = Redis.from_url(REDIS_URL, decode_responses=True)
    second = Redis.from_url(REDIS_URL, decode_responses=True)
    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="development",
            jwt_secret_key="real-redis-proxy-budget-test-secret-material",
            rate_limit_redis_url=REDIS_URL,
            trusted_proxy_cidrs="10.10.0.0/16",
            ai_account_daily_limit=1,
            ai_session_daily_limit=5,
            ai_global_daily_limit=20,
            ai_budget_namespace=namespace,
        ),
    )
    request_a = _proxy_request(
        "10.10.0.8", "198.51.100.10", first
    )
    request_a_other_instance = _proxy_request(
        "10.10.0.9", "198.51.100.10", second
    )
    request_b = _proxy_request(
        "10.10.0.8", "198.51.100.11", second
    )

    async def reserve(request):
        try:
            await _reserve_ai_budget(request, None, None)
            return True
        except HTTPException as error:
            if error.status_code != 429:
                raise
            return False

    try:
        assert await reserve(request_a) is True
        assert await reserve(request_a_other_instance) is False
        assert await reserve(request_b) is True
    finally:
        pattern = f"{namespace}:ai-budget:{{shared}}:*"
        keys = [key async for key in first.scan_iter(match=pattern)]
        if keys:
            await first.delete(*keys)
        await first.aclose()
        await second.aclose()


def _proxy_request(proxy_ip, forwarded_ip, redis_client):
    from types import SimpleNamespace
    from starlette.requests import Request

    app = SimpleNamespace(state=SimpleNamespace(rate_limit_redis=redis_client))
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/scoping/",
        "headers": [(b"x-forwarded-for", forwarded_ip.encode("ascii"))],
        "client": (proxy_ip, 12345),
        "app": app,
    })


@pytest.mark.anyio
async def test_ai_budget_fails_closed_during_redis_outage_and_recovers(
    monkeypatch,
):
    from fastapi import HTTPException
    from redis.asyncio import Redis
    from sqlalchemy.engine import make_url

    target = make_url(REDIS_URL)
    if target.host not in {"127.0.0.1", "localhost", "::1"} or target.database != "15":
        pytest.skip("AI budget integration requires disposable localhost Redis DB 15.")
    from config.settings import Settings
    import config.settings as settings_module

    redis = Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=0.1,
    )
    control = Redis.from_url(REDIS_URL, decode_responses=True)
    namespace = f"agencyforge-test-outage-{uuid.uuid4().hex}"
    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            database_url="postgresql+psycopg://agency:secret@localhost/agencyforge",
            jwt_secret_key="real-redis-ai-budget-test-secret-material",
            rate_limit_redis_url=REDIS_URL,
            ai_account_daily_limit=2,
            ai_session_daily_limit=2,
            ai_global_daily_limit=5,
            ai_budget_namespace=namespace,
        ),
    )
    request = SimpleNamespace(
        client=SimpleNamespace(host="127.0.0.1"),
        app=SimpleNamespace(state=SimpleNamespace(rate_limit_redis=redis)),
    )

    try:
        await control.ping()
        await control.execute_command("CLIENT", "PAUSE", 500, "ALL")
        with pytest.raises(HTTPException) as error:
            await _reserve_ai_budget(request, 9021001, None)
        assert error.value.status_code == 503

        await asyncio.sleep(0.6)
        await _reserve_ai_budget(request, 9021001, None)
        await _reserve_ai_budget(request, 9021001, None)
        with pytest.raises(HTTPException) as limited:
            await _reserve_ai_budget(request, 9021001, None)
        assert limited.value.status_code == 429
    finally:
        pattern = f"{namespace}:ai-budget:{{shared}}:*"
        keys = [key async for key in control.scan_iter(match=pattern)]
        if keys:
            await control.delete(*keys)
        await redis.aclose()
        await control.aclose()


@pytest.fixture
def anyio_backend():
    return "asyncio"
