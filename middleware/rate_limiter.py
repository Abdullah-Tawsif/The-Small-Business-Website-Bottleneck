import time
from collections import defaultdict
from threading import Lock

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from config.settings import get_settings


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
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )
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
