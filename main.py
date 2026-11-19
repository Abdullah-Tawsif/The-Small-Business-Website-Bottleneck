from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Scopewise", version="0.1.0")
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

@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok"}
