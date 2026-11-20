
# AgencyForge — Small Business Website Bottleneck

AgencyForge is a FastAPI-based platform designed to help small businesses
plan and develop websites through structured inquiries, package-based
pricing, customer lead management and AI-assisted project scoping.

## Features

- User registration and login
- JWT authentication using HttpOnly cookies or Bearer tokens
- Secure password hashing using scrypt
- Database-backed administrator authorization
- Public website package listing
- Project price estimation
- Customer inquiry and lead management
- AI-assisted project scoping
- Administrator analytics API
- Administrator user management
- Staff account activation and deactivation
- Server-rendered pages using Jinja2
- SQLite development database with PostgreSQL support

## Technology Stack

- Python
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite / PostgreSQL
- JWT authentication
- Scrypt password hashing
- Jinja2
- HTML, CSS and JavaScript

## Getting Started

Prerequisites: Python 3.12 (the CI-tested version) and pip.

### 1. Clone the repository

```bash
git clone https://github.com/Abdullah-Tawsif/The-Small-Business-Website-Bottleneck.git

cd The-Small-Business-Website-Bottleneck
```

### 2. Create a virtual environment

Windows:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example environment file:

Windows:

```powershell
Copy-Item .env.example .env
```

Linux / macOS:

```bash
cp .env.example .env
```

Generate a secure JWT secret:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Replace the placeholder value of `JWT_SECRET_KEY` in `.env`.

Never commit your actual `.env` file or production secrets.

The application uses SQLite by default. PostgreSQL can be configured through `DATABASE_URL`.

### 5. Create and migrate the database

Schema changes are applied through Alembic. The application checks that the
database is at the latest revision and never creates or upgrades tables during
startup.

For the example persistent local SQLite database, pass the target explicitly
and opt in to a non-`/tmp` migration target:

```bash
DATABASE_URL=sqlite:///./agencyforge-dev.sqlite ALLOW_NON_TMP_MIGRATIONS=1 alembic upgrade head
```

PowerShell:

```powershell
$env:ALLOW_NON_TMP_MIGRATIONS = "1"
$env:DATABASE_URL = "sqlite:///./agencyforge-dev.sqlite"
alembic upgrade head
```

For tests and disposable development databases, use a separate path under
`/tmp`; migrations to that path do not need the opt-in. The migration runner
refuses any file named `agencyforge.db` and never selects a URL implicitly.

### 6. Seed the website packages

The package API starts empty on a new database. Load the sample packages with:

```bash
python seed_packages.py
```

Seeding is idempotent: existing package slugs are preserved and not overwritten.

### 7. Create the initial administrator

Public registration creates staff accounts only.

To create the first administrator, run:

```bash
python create_admin.py
```

The script prompts for the administrator's name, email and password. Password input is hidden.

It will not overwrite an existing account.

### 8. Start the application

```bash
uvicorn main:app --reload
```

Open:

http://127.0.0.1:8000

API documentation:

http://127.0.0.1:8000/docs

## Application Routes

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Register a staff account |
| POST | `/api/auth/login` | Authenticate a user |
| POST | `/api/auth/logout` | End the browser session |
| GET | `/api/auth/me` | Get current user information |

### Public Packages and Pricing

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/packages/` | List active packages |
| POST | `/api/packages/estimate` | Calculate project pricing |

### Customer Leads

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/leads/` | Submit an inquiry |
| GET | `/api/leads/` | List leads (admin only) |
| GET | `/api/leads/{lead_id}` | Retrieve a lead (admin only) |
| PATCH | `/api/leads/{lead_id}/status` | Update lead status (admin only) |

### AI Project Scoping

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/scoping/` | Create or continue an AI scoping session |

### Administrator

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/admin/users` | List users with pagination |
| PATCH | `/api/admin/users/{user_id}/status` | Activate or deactivate an account |
| GET | `/api/admin/analytics` | Retrieve analytics for a date range |

Administrator endpoints require an authenticated, active administrator account.

### Web Pages

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Home page |
| GET | `/login` | Login page |
| GET | `/register` | Registration page |
| GET | `/inquiry` | Inquiry workflow |
| GET | `/packages` | Package selection redirect |
| GET | `/dashboard` | Protected dashboard |
| GET | `/admin` | Administrator-only overview |
| GET | `/health` | Process liveness check |
| GET | `/ready` | Database schema and configured Redis readiness check |

## Authentication and Security

- Passwords are stored using salted scrypt hashes.
- Access tokens are signed JWTs.
- Browser authentication uses an HttpOnly cookie.
- Bearer token authentication is also supported.
- Current user identity and account status are checked against the database.
- Administrator authorization uses the current database role, not the JWT role claim.
- Inactive users cannot access protected endpoints.
- Public registration cannot assign administrator privileges.
- Administrator management endpoints reject unauthorized users.
- Password hashes are excluded from user API responses.

## Project Structure

```text
.
├── config/
│   └── settings.py
├── database/
│   └── database.py
├── middleware/
│   ├── auth_middleware.py
│   ├── error_handlers.py
│   ├── rate_limiter.py
│   └── request_size_limit.py
├── models/
├── routes/
│   ├── admin.py
│   ├── analytics.py
│   ├── auth.py
│   ├── leads.py
│   ├── public.py
│   └── scoping.py
├── schemas/
├── scripts/
├── services/
├── static/
├── templates/
├── tests/
├── utils/
├── create_admin.py
└── main.py
```

## Database

SQLAlchemy manages application database operations.

The application supports:

- SQLite for local development.
- PostgreSQL for production deployments.

Version-controlled Alembic migrations define the schema. Initialize a fresh
database with `alembic upgrade head`; ordinary application startup checks the
revision and fails with an actionable message when migration is needed. Startup
does not modify schema.

To add a schema change, create a reviewed revision, inspect its upgrade and
downgrade operations, test it against fresh and representative databases, and
run `alembic upgrade head` as a separate release step. Back up persistent
databases first. The initial baseline downgrade is intentionally refused
because dropping those tables would destroy application records.

For an existing database created by the earlier `create_all()` startup, first
take and verify a backup and compare its tables, columns, indexes, and
constraints with the `4b0699abd0b3` baseline revision. If they match, stamp
that baseline and then run `alembic upgrade head`; the current follow-up only
adds an index and preserves records. Stamping does not modify tables or
records. Run `alembic check` after the upgrade. All non-`/tmp` migration targets require
`ALLOW_NON_TMP_MIGRATIONS=1`. Never point the migration command at an
unverified database.

## Deployment readiness

No deployment manifest is included. Production requires a managed database,
an explicit migration release step, HTTPS termination, a strong JWT secret,
and shared Redis/Valkey rate-limit storage. The app requires
`RATE_LIMIT_REDIS_URL` in production and rejects requests if Redis becomes
unavailable. Configure and secure that service independently; use a `rediss://`
URL where supported. The application does not trust forwarded client IP
headers, so configure a trusted proxy policy before changing that behavior.

## Running Tests

Run the test suite using:

```bash
python -m pytest -q
```

Run a specific test file:

```bash
python -m pytest tests/test_security.py -v
```

## Environment Variables

| Variable | Purpose |
|---|---|
| `APP_NAME` | Application name |
| `ENVIRONMENT` | Development or production |
| `DATABASE_URL` | Database connection |
| `JWT_SECRET_KEY` | JWT signing secret |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT lifetime |
| `ACCESS_TOKEN_COOKIE_NAME` | Authentication cookie name |
| `RATE_LIMIT_REQUESTS` | Rate limit request count |
| `RATE_LIMIT_WINDOW_SECONDS` | Rate limit window |
| `RATE_LIMIT_REDIS_URL` | Redis/Valkey URL for shared rate limits (required in production) |
| `MAX_REQUEST_BODY_BYTES` | Maximum request body size |

Migration commands additionally require an explicit `DATABASE_URL`. Set
`ALLOW_NON_TMP_MIGRATIONS=1` only after verifying a persistent target; migration
commands otherwise accept only disposable SQLite files under `/tmp`.

## Security Notes

- Use a unique, strong JWT secret in production.
- Set `ENVIRONMENT=production` to enable secure session cookies.
- Login and registration, plus state-changing requests authenticated with the session cookie, require matching Origin or Referer evidence. Cookie-authenticated writes must also submit the readable `csrf_token` cookie in the `X-CSRF-Token` header. The dashboard and admin page do this automatically.
- Never expose password hashes or secret environment values.
- Never use public registration to create administrators.
- Restrict administrator access to authorized personnel.
- Use HTTPS in production.

A Content Security Policy is deferred because current pages use inline scripts
and styles plus Google Fonts and the externally hosted Lucide script. Adding a
policy without first moving inline code to nonce- or hash-based assets would
either break those pages or require broad allowances that provide little
protection.

## Development

The application uses a modular structure:

- `routes/` handles HTTP endpoints.
- `services/` contains business logic.
- `models/` defines database entities.
- `schemas/` defines request and response validation.
- `middleware/` handles authentication and application-level middleware.
- `config/` manages environment settings.

This separation allows the backend, database, AI and frontend components to be developed independently.

## Deferred product decisions

These features are intentionally not implemented until their behavior and access rules are defined:

- **Password recovery:** choose a verified email delivery provider, identity verification method, one-time token format and expiry, invalidation behavior, and request throttling.
- **AI session ownership and history:** define whether sessions belong to an account, a customer inquiry, or neither; who can view them; how long they are retained; and how deletion works.
- **Account controls:** specify which account actions users or administrators may take and the confirmation, audit, and recovery behavior for each action.
- **Open sessions metric:** identify the qualifying AI session statuses and whether the count includes all users or a scoped subset.
- **User template:** define its purpose, intended audience, route, and authorization rules before serving it.
