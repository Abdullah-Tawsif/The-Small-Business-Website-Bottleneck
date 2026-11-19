# AgencyForge — Commit 4: FastAPI Authentication & Pages

## Run locally (Windows PowerShell / VS Code terminal)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and replace `JWT_SECRET_KEY` with a random secret (at least 32 characters). Generate one with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated value after `JWT_SECRET_KEY=` in `.env`, save, then start the app:

```powershell
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`, then use **Register** or visit `/register`. After registration or login, the app redirects to the protected `/dashboard` page. The default local database is SQLite (`agencyforge.db`), created automatically at startup.

## Authentication endpoints

- `POST /api/auth/register` — create account and sign in.
- `POST /api/auth/login` — sign in.
- `GET /api/auth/me` — return the current signed-in user.
- `POST /api/auth/logout` — clear the session cookie.
- `GET /dashboard` — protected starter user page.

The browser session uses an HttpOnly JWT cookie. Passwords are stored as salted scrypt hashes. This is the fourth-commit backend integration; frontend styling can be adjusted in `templates/` and `static/css/` without changing the API contract.

## Tests

```powershell
python -m pytest -q
```
