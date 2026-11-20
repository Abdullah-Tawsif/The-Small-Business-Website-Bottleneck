
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

Development can use SQLite. Production must set an explicit PostgreSQL
`DATABASE_URL`; startup rejects a missing URL, SQLite, and incomplete PostgreSQL
configuration. The PostgreSQL URL uses the installed psycopg v3 driver, for
example `postgresql+psycopg://agencyforge:...@db.example/agencyforge`.

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

For tests and disposable development databases, use a separate path under the
platform temporary directory; migrations there do not need the opt-in. The
migration runner refuses the protected `agencyforge.db` and never selects a URL
implicitly. Persistent development, staging, and PostgreSQL targets require an
explicit `ALLOW_NON_TMP_MIGRATIONS=1` for the migration command only.

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
| GET | `/user` | Protected user project workspace |
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

For an existing SQLite database created before Alembic, use the guarded backup
copy adoption tool. Never migrate `agencyforge.db` directly:

1. Stop application writers and create a separate backup file outside the
   repository. Keep the original and backup unchanged; verify the backup with
   `sqlite3 /safe/agencyforge-legacy-backup.sqlite 'PRAGMA integrity_check;'`.
2. Run adoption against the backup copy, using the required distinct target
   filename:

   ```bash
   python -m database.adopt_legacy \
     --backup /safe/agencyforge-legacy-backup.sqlite \
     --target /tmp/agencyforge-legacy-import.sqlite
   ```

3. The tool copies the backup, verifies baseline tables and columns before
   stamping, applies later Alembic migrations, runs `alembic check`, and
   compares application row counts. Review the output and application records
   before using the imported copy.
4. For a persistent target outside the platform temporary directory, choose an
   isolated destination with the exact `agencyforge-legacy-import.sqlite`
   filename and pass `--allow-non-temp`. Preserve both source backup and
   original during verification. After a tested recovery plan is in place,
   configure the application to use the verified copy; never overwrite the
   original database as part of adoption.
5. If validation fails, stop and restore from the verified backup to a new
   disposable copy. Do not stamp a partial schema or retry against the original.

This procedure adopts a legacy SQLite schema. It is not a SQLite-to-PostgreSQL
data transfer; that transfer path is not implemented by this application.

## Deployment readiness

No deployment manifest is included. Production requires managed PostgreSQL and
Redis, an explicit migration release step, HTTPS termination, secure secrets,
monitoring, and tested backup/restore procedures. `RATE_LIMIT_REDIS_URL` is
required in production and protected writes fail closed if shared Redis is
unavailable. Use a private authenticated Redis endpoint and `rediss://` where
supported. Forwarded client IPs are honored only when the socket peer is inside
`TRUSTED_PROXY_CIDRS`; configure only actual ingress networks and block direct
public access to workers.

Rate budgets are separated for authentication, public writes, AI scoping,
ordinary APIs, administration, and readiness. Static assets have caching and do
not consume those budgets. Login also has short-lived, shared, account-keyed
failure counters and progressive delay. AI requests have account, session or
guest, and global daily request caps. These request caps need provider-side
spending limits and alerts too. `/health` is process liveness; `/ready` checks
database and configured Redis with a short bounded cache.

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
| `AUTH_RATE_LIMIT_REQUESTS` | Requests per authentication IP window |
| `PUBLIC_WRITE_RATE_LIMIT_REQUESTS` | Public inquiry/write request budget |
| `AI_RATE_LIMIT_REQUESTS` | AI endpoint IP request budget |
| `API_RATE_LIMIT_REQUESTS` | Ordinary application API request budget |
| `ADMIN_RATE_LIMIT_REQUESTS` | Administrative request budget |
| `READINESS_RATE_LIMIT_REQUESTS` | Readiness probe request budget |
| `TRUSTED_PROXY_CIDRS` | Comma-separated trusted ingress networks |
| `AI_ACCOUNT_DAILY_LIMIT` | Daily AI requests per account or guest source |
| `AI_SESSION_DAILY_LIMIT` | Daily AI requests per existing session/capability |
| `AI_GLOBAL_DAILY_LIMIT` | Overall daily AI request ceiling |
| `MAX_REQUEST_BODY_BYTES` | Maximum request body size |

Migration commands additionally require an explicit `DATABASE_URL`. Set
`ALLOW_NON_TMP_MIGRATIONS=1` only after verifying a persistent target; migration
commands otherwise accept only disposable SQLite files under the platform
temporary directory.

## Security Notes

- Use a unique, strong JWT secret in production.
- Set `ENVIRONMENT=production` to enable secure session cookies.
- Login and registration, plus state-changing requests authenticated with the session cookie, require matching Origin or Referer evidence. Cookie-authenticated writes must also submit the readable `csrf_token` cookie in the `X-CSRF-Token` header. The dashboard and admin page do this automatically.
- Never expose password hashes or secret environment values.
- Never use public registration to create administrators.
- Restrict administrator access to authorized personnel.
- Use HTTPS in production.

A restrictive Content Security Policy is still deferred because the inquiry,
dashboard, and administrator pages use inline scripts and styles. The icon
renderer is local and web fonts use system stacks. Add a CSP only after moving
remaining inline code to nonce- or hash-based assets and testing every page.

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
- **Open sessions metric:** identify the qualifying AI session statuses and whether the count includes all users or a scoped subset.
- **AI history retention and deletion:** define conversation retention, deletion, and customer data export behavior beyond the current session access and expiry checks.
- **Account recovery and audit history:** define recovery and audit behavior for administrator account activation changes before adding broader account controls.
