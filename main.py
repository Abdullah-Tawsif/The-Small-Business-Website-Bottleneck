"""AgencyForge FastAPI application entry point."""

import logging
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis

from config.settings import get_settings, validate_runtime_settings
from database.database import verify_schema
from middleware.auth_middleware import get_current_admin_user, get_current_user
from middleware.csrf_protection import CSRFProtectionMiddleware
from middleware.error_handlers import register_error_handlers
from middleware.rate_limiter import RateLimitMiddleware
from middleware.request_size_limit import RequestSizeLimitMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from models.user import User
from routes.admin import router as admin_router
from routes.analytics import router as analytics_router
from routes.auth import router as auth_router
from routes.leads import router as leads_router
from routes.public import router as public_router
from routes.scoping import router as scoping_router

BASE_DIR = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)
_READINESS_CACHE_TTL = 2.0
_READINESS_CACHE: tuple[float, bool] | None = None
_READINESS_LOCK = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Validate runtime settings and manage shared service connections."""
    validate_runtime_settings()
    verify_schema()
    settings = get_settings()
    redis_client = None
    if settings.rate_limit_redis_url:
        redis_client = Redis.from_url(
            settings.rate_limit_redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )
        try:
            await redis_client.ping()
        except Exception as exc:
            await redis_client.aclose()
            redis_client = None
            if settings.environment.lower() == "production":
                raise RuntimeError(
                    "Shared rate-limit storage is unavailable."
                ) from exc
            logger.warning(
                "Shared rate-limit storage is unavailable; using process-local limits."
            )
    app.state.rate_limit_redis = redis_client
    try:
        yield
    finally:
        if redis_client is not None:
            await redis_client.aclose()


app = FastAPI(
    title="AgencyForge",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
register_error_handlers(app)

# API routers. Keep route registration centralized here.
app.include_router(auth_router)
app.include_router(public_router)
app.include_router(scoping_router)
app.include_router(leads_router)
app.include_router(analytics_router)
app.include_router(admin_router)

# Static assets and server-rendered pages.
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "static"),
    name="static",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="home/index.html",
        context={},
    )


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={},
    )


@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={},
    )


@app.get("/inquiry", include_in_schema=False)
async def inquiry_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="inquiry/index.html",
        context={},
    )


@app.get("/packages", include_in_schema=False)
async def packages_page():
    """The package selection lives in the inquiry workflow for now."""
    return RedirectResponse(
        url="/inquiry#package-recommendation",
        status_code=302,
    )


@app.get("/dashboard", include_in_schema=False)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={"user": user},
    )


@app.get("/user", include_in_schema=False)
async def user_workspace(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Serve the signed-in user's project workspace."""
    return templates.TemplateResponse(
        request=request,
        name="user/user.html",
        context={"user": user},
    )


@app.get("/admin", include_in_schema=False)
async def admin_page(
    request: Request,
    user: User = Depends(get_current_admin_user),
):
    """Serve the administrator workspace to active administrators only."""
    return templates.TemplateResponse(
        request=request,
        name="admin/admin.html",
        context={"user": user},
    )


@app.get("/health", include_in_schema=False)
async def health():
    """Return process liveness without querying shared dependencies."""
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
async def readiness(request: Request):
    """Report bounded, briefly cached DB and configured Redis availability."""
    global _READINESS_CACHE
    now = time.monotonic()
    if _READINESS_CACHE and now - _READINESS_CACHE[0] < _READINESS_CACHE_TTL:
        healthy = _READINESS_CACHE[1]
    else:
        async with _READINESS_LOCK:
            now = time.monotonic()
            if _READINESS_CACHE and now - _READINESS_CACHE[0] < _READINESS_CACHE_TTL:
                healthy = _READINESS_CACHE[1]
            else:
                healthy = True
                try:
                    verify_schema()
                    settings = get_settings()
                    if settings.rate_limit_redis_url:
                        redis_client = getattr(
                            request.app.state, "rate_limit_redis", None
                        )
                        if redis_client is None:
                            raise RuntimeError(
                                "Shared rate-limit storage is unavailable."
                            )
                        await redis_client.ping()
                except Exception:
                    healthy = False
                    logger.error("Application readiness check failed.")
                _READINESS_CACHE = (time.monotonic(), healthy)
    if not healthy:
        raise HTTPException(
            status_code=503,
            detail="Service is temporarily unavailable.",
        )
    return {"status": "ready"}
