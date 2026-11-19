
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
- Administrator analytics dashboard
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

### 5. Create the initial administrator

Public registration creates staff accounts only.

To create the first administrator, run:

```bash
python create_admin.py
```

The script prompts for the administrator's name, email and password. Password input is hidden.

It will not overwrite an existing account.

### 6. Start the application

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
| GET | `/health` | Application health check |

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
│   └── rate_limiter.py
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

Database tables are initialized during application startup.

## Running Tests

Run the test suite using:

```bash
python -m pytest -q
```

Run a specific test file:

```bash
python -m pytest tests/test_auth.py -v
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
| `MAX_REQUEST_BODY_BYTES` | Maximum request body size |

## Security Notes

- Use a unique, strong JWT secret in production.
- Set `ENVIRONMENT=production` to enable secure session cookies.
- Never expose password hashes or secret environment values.
- Never use public registration to create administrators.
- Restrict administrator access to authorized personnel.
- Use HTTPS in production.

## Development

The application uses a modular structure:

- `routes/` handles HTTP endpoints.
- `services/` contains business logic.
- `models/` defines database entities.
- `schemas/` defines request and response validation.
- `middleware/` handles authentication and application-level middleware.
- `config/` manages environment settings.

This separation allows the backend, database, AI and frontend components to be developed independently.
