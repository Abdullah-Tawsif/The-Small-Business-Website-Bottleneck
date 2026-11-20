import hashlib
import logging
import time
from collections import defaultdict
from threading import Lock

from redis.exceptions import RedisError
from utils.security import InvalidTokenError, decode_access_token
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.settings import get_settings
from utils.client_identity import get_client_ip

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

    async def dispatch(
        self,
        request: Request,
        call_next,
        *,
        policy: str = "application-api",
        limit: int | None = None,
        client_ip: str | None = None,
    ):
        settings = get_settings()
        # Use the socket peer address. Do not trust X-Forwarded-For unless
        # a trusted proxy is explicitly configured.
        client_ip = client_ip or (request.client.host if request.client else "unknown")
        now = time.monotonic()
        window = settings.rate_limit_window_seconds
        limit = limit or settings.rate_limit_requests
        key = (f"{policy}:{client_ip}", int(now // window))

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
    local now = redis.call('TIME')
    local seconds = tonumber(now[1])
    local window = tonumber(ARGV[1])
    local window_id = tostring(math.floor(seconds / window))
    local fields = redis.call('HKEYS', KEYS[1])
    for _, field in ipairs(fields) do
      if field ~= window_id then redis.call('HDEL', KEYS[1], field) end
    end
    local count = redis.call('HINCRBY', KEYS[1], window_id, 1)
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
    local retry = window - (seconds % window)
    return {count, retry}
    """

    def __init__(self, app):
        super().__init__(app)
        self._local = InMemoryRateLimitMiddleware(app)
        self._store_failure_logged = False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path == "/health":
            return await call_next(request)

        settings = get_settings()
        policy, limit = self._policy(path, settings, request.method)
        client_ip = self._client_ip(request, settings.trusted_proxy_cidrs)
        rate_identity = client_ip
        if policy == "administration":
            rate_identity = self._admin_rate_identity(request, client_ip, settings)
        if path.startswith("/static/"):
            response = await call_next(request)
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
            return response

        redis_url = settings.rate_limit_redis_url
        if not redis_url:
            return await self._local.dispatch(
                request,
                call_next,
                policy=policy,
                limit=limit,
                client_ip=rate_identity,
            )

        try:
            redis_client = getattr(request.app.state, "rate_limit_redis", None)
            if redis_client is None:
                raise RuntimeError("Shared rate-limit client is unavailable.")
            client_key = hashlib.sha256(rate_identity.encode("utf-8")).hexdigest()
            window = settings.rate_limit_window_seconds
            key = f"agencyforge:rate-limit:v3:{{{client_key}}}:{policy}:windows"
            # Redis TIME, window selection, increment, and expiry are one atomic
            # operation, so network delay cannot move a request into a stale key.
            count, ttl = await redis_client.eval(
                self._INCREMENT_SCRIPT,
                1,
                key,
                window,
                window * 2,
            )
            self._store_failure_logged = False
            if int(count) > limit:
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
            return await self._local.dispatch(
                request,
                call_next,
                policy=policy,
                limit=limit,
                client_ip=rate_identity,
            )

        return await call_next(request)

    @staticmethod
    def _policy(path: str, settings, method: str = "GET") -> tuple[str, int]:
        if path.startswith("/static/"):
            return "static", settings.api_rate_limit_requests
        if path == "/ready":
            return "readiness", settings.readiness_rate_limit_requests
        if path.startswith("/api/auth/"):
            return "authentication", settings.auth_rate_limit_requests
        if path.startswith("/api/scoping/"):
            return "ai", settings.ai_rate_limit_requests
        if path.startswith("/api/admin/") or path == "/admin":
            return "administration", settings.admin_rate_limit_requests
        if path.startswith("/api/leads/") or path == "/api/leads":
            if method.upper() == "POST" and path in {"/api/leads", "/api/leads/"}:
                return "public-write", settings.public_write_rate_limit_requests
            return "administration", settings.admin_rate_limit_requests
        return "application-api", settings.api_rate_limit_requests

    @staticmethod
    def _client_ip(request: Request, trusted_proxy_cidrs: str) -> str:
        return get_client_ip(request, trusted_proxy_cidrs)

    @staticmethod
    def _admin_rate_identity(request: Request, fallback_ip: str, settings) -> str:
        """Partition administrator budgets by signed-in subject when possible."""
        token = request.cookies.get(settings.access_token_cookie_name)
        authorization = request.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization.split(None, 1)[1]
        if token:
            try:
                subject = decode_access_token(token).get("sub")
                if subject:
                    return f"admin-user:{subject}"
            except (InvalidTokenError, ValueError, TypeError):
                pass
        return f"admin-ip:{fallback_ip}"
