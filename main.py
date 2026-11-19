from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database.database import init_db
from middleware.auth_middleware import get_current_user
from middleware.error_handlers import register_error_handlers
from middleware.rate_limiter import InMemoryRateLimitMiddleware
from models.ai_session import AISession
from models.user import User
from routes.analytics import router as analytics_router
from routes.auth import router as auth_router
from routes.leads import router as leads_router
from routes.public import router as public_router
from routes.scoping import router as scoping_router

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Importing the route modules above registers their SQLAlchemy models
    # before create_all is called during application startup.
    init_db()
    yield


app = FastAPI(title="AgencyForge", version="0.2.0", lifespan=lifespan)
app.add_middleware(InMemoryRateLimitMiddleware)
register_error_handlers(app)

# API routers
app.include_router(auth_router)
app.include_router(public_router)
app.include_router(scoping_router)
app.include_router(leads_router)
app.include_router(analytics_router)

# Static files and templates
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
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


@app.get("/dashboard", include_in_schema=False)
async def dashboard(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="dashboard/index.html",
        context={"user": user},
    )


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
