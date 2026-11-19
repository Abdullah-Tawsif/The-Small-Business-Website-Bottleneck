from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from middleware.auth_middleware import get_current_user
from middleware.error_handlers import register_error_handlers
from middleware.rate_limiter import InMemoryRateLimitMiddleware
from models.user import User
from database.database import init_db
from routes.auth import router as auth_router

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="AgencyForge", version="0.2.0", lifespan=lifespan)
app.add_middleware(InMemoryRateLimitMiddleware)
register_error_handlers(app)
app.include_router(auth_router)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@app.get("/", include_in_schema=False)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="home/index.html", context={})

@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth/login.html", context={})

@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="auth/register.html", context={})

@app.get("/dashboard", include_in_schema=False)
async def dashboard(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="dashboard/index.html", context={"user": user})

@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
