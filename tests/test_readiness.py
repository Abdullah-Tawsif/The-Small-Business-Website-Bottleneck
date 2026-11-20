import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import main
from config.settings import Settings
from middleware.rate_limiter import RateLimitMiddleware


def request_for(redis=None):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/ready",
            "headers": [],
            "client": ("192.0.2.10", 1234),
            "app": SimpleNamespace(state=SimpleNamespace(rate_limit_redis=redis)),
        }
    )


def test_readiness_caches_expensive_schema_probe_and_returns_ready(monkeypatch):
    calls = 0

    def verify():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(main, "verify_schema", verify)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(main, "_READINESS_CACHE", None)

    async def run():
        results = await asyncio.gather(
            *(main.readiness(request_for()) for _ in range(24))
        )
        return results

    assert asyncio.run(run()) == [{"status": "ready"}] * 24
    assert calls == 1
    assert RateLimitMiddleware._policy("/ready", Settings(_env_file=None))[0] == "readiness"


def test_readiness_reports_dependency_failure_and_recovery(monkeypatch):
    healthy = False

    def verify():
        if not healthy:
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "verify_schema", verify)
    monkeypatch.setattr(main, "get_settings", lambda: Settings(_env_file=None))
    monkeypatch.setattr(main, "_READINESS_CACHE", None)
    monkeypatch.setattr(main, "_READINESS_CACHE_TTL", 0)

    async def failing():
        with pytest.raises(HTTPException) as error:
            await main.readiness(request_for())
        assert error.value.status_code == 503

    asyncio.run(failing())
    healthy = True
    assert asyncio.run(main.readiness(request_for())) == {"status": "ready"}


def test_readiness_tracks_redis_failure_and_recovery(monkeypatch):
    class RedisProbe:
        available = False

        async def ping(self):
            if not self.available:
                raise OSError("redis unavailable")
            return True

    redis = RedisProbe()
    monkeypatch.setattr(main, "verify_schema", lambda: None)
    monkeypatch.setattr(
        main,
        "get_settings",
        lambda: Settings(_env_file=None, rate_limit_redis_url="redis://localhost/0"),
    )
    monkeypatch.setattr(main, "_READINESS_CACHE", None)
    monkeypatch.setattr(main, "_READINESS_CACHE_TTL", 0)

    async def failing():
        with pytest.raises(HTTPException) as error:
            await main.readiness(request_for(redis))
        assert error.value.status_code == 503

    asyncio.run(failing())
    redis.available = True
    assert asyncio.run(main.readiness(request_for(redis))) == {"status": "ready"}
