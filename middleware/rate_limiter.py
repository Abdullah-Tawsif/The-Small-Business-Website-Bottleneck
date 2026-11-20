import hashlib
import logging
import time
from collections import defaultdict
from threading import Lock

from redis.exceptions import RedisError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.settings import get_settings

logger = logging.getLogger(__name__)


def _limited_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please try again later."},
        headers={"Retry-After": str(max(1, retry_after))},
    )


class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Small single-process fixed-window limiter for the hackathon prototype.
    For multi-worker/production deployment, replace storage with Redis.
    """

    def __init__(self, app):
        super().__init__(app)
        self._buckets = defaultdict(lambda: [0, 0.0])
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        # Use the socket peer address. Do not trust X-Forwarded-For unless
        # a trusted proxy is explicitly configured.
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_requests
        key = (client_ip, int(now // window))

        with self._lock:
            count, _ = self._buckets[key]
            if count >= limit:
                retry_after = max(1, window - int(now % window))
                return _limited_response(retry_after)
            self._buckets[key] = [count + 1, now]

            # Periodically discard old windows to keep memory bounded.
            if now - self._last_cleanup > window:
                current_window = int(now // window)
                self._buckets = defaultdict(
                    lambda: [0, 0.0],
                    {k: v for k, v in self._buckets.items() if k[1] >= current_window - 1},
                )
                self._last_cleanup = now

        return await call_next(request)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Share fixed-window request limits through Redis when configured.

    Development uses the existing bounded in-process limiter when no Redis
    URL is configured. Production requires Redis and fails closed if it is
    unavailable, so every worker enforces the same limit.
    """

    _INCREMENT_SCRIPT = """
    local count = redis.call('INCR', KEYS[1])
    if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
    return {count, redis.call('TTL', KEYS[1])}
    """

    def __init__(self, app):
        super().__init__(app)
        self._local = InMemoryRateLimitMiddleware(app)
        self._store_failure_logged = False

    async def dispatch(self, request: Request, call_next):
        # Liveness/readiness probes must reach their handlers even when the
        # shared rate-limit store is unavailable. The readiness handler checks
        # its own dependencies and can return an accurate 503 when necessary.
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)

        settings = get_settings()
        redis_url = settings.rate_limit_redis_url
        if not redis_url:
            return await self._local.dispatch(request, call_next)

        try:
            redis_client = getattr(request.app.state, "rate_limit_redis", None)
            if redis_client is None:
                raise RuntimeError("Shared rate-limit client is unavailable.")
            client_ip = request.client.host if request.client else "unknown"
            client_key = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()
            window = settings.rate_limit_window_seconds
            # Use Redis time so workers with different host clocks share the
            # same window boundary.
            redis_time = await redis_client.time()
            window_id = int(redis_time[0]) // window
            key = f"agencyforge:rate-limit:v1:{client_key}:{window_id}"
            count, ttl = await redis_client.eval(
                self._INCREMENT_SCRIPT,
                1,
                key,
                window * 2,
            )
            self._store_failure_logged = False
            if int(count) > settings.rate_limit_requests:
                return _limited_response(int(ttl) if int(ttl) > 0 else window)
        except (RedisError, RuntimeError, OSError, ValueError, TypeError):
            if settings.environment.lower() == "production":
                # Keep the details out of the client response and avoid
                # logging URLs, which may contain Redis credentials.
                if not self._store_failure_logged:
                    logger.error(
                        "Shared rate-limit store unavailable; request rejected."
                    )
                    self._store_failure_logged = True
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Request protection is temporarily unavailable."},
                    headers={"Retry-After": str(settings.rate_limit_window_seconds)},
                )
            if not self._store_failure_logged:
                logger.warning(
                    "Shared rate-limit store unavailable; using process-local limits."
                )
                self._store_failure_logged = True
            return await self._local.dispatch(request, call_next)

        return await call_next(request)
