# AgencyForge — Security branch starter

## Implemented in this starter
- Environment-backed settings (`config/settings.py`)
- scrypt password hashing and JWT utilities (`utils/security.py`)
- Strict Pydantic login/registration payload models (`utils/validators.py`)
- Single-process IP fixed-window rate limiter (`middleware/rate_limiter.py`)
- Non-leaking FastAPI exception handlers (`middleware/error_handlers.py`)
- Initial security unit tests (`tests/test_security.py`)

## Integration still required
- Register `InMemoryRateLimitMiddleware` and `register_error_handlers(app)` in `main.py`.
- Implement authentication dependencies and role checks after confirming Person 2's SQLAlchemy `User` model and database session interface.
- Implement `services/auth_service.py` and `routes/auth.py` against the agreed user model/schema.
- Configure PostgreSQL and run the full application integration tests.
- Add CSRF protection if authentication is moved to browser cookies. For bearer tokens in the Authorization header, do not store tokens in localStorage without an explicit threat-model decision.

## Important limitations
The in-memory rate limiter is for a single-process prototype. It does not coordinate limits across multiple workers or machines; use Redis for that deployment model. The current limiter is global per client IP and should be tuned for the demo.

JWT access tokens are not inherently revocable. Keep them short-lived and check user active/role state against the database for protected admin operations. Do not treat the role claim alone as the only authorization source for sensitive actions.

## Frontend handoff
No HTML, CSS, JavaScript, templates, or static assets were created or modified. Person 3 can add those independently.
