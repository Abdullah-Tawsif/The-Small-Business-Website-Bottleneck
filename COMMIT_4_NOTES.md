Commit 4 integrates FastAPI registration and login with SQLite-backed user storage, scrypt password hashing, and JWT HttpOnly session cookies.
Adds protected dashboard access, current-user and logout endpoints, plus login/register forms wired to the backend.
Run locally with `pip install -r requirements.txt` and `uvicorn main:app --reload` after creating `.env` from `.env.example`.
