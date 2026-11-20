# AgencyForge security and operations handoff

This handoff describes the current FastAPI application, its deployment boundaries,
and the checks still required before production use.

## Authentication and authorization

- Passwords are hashed with Python scrypt (`utils/security.py`). Password hashes
  are not returned from user APIs.
- Browser sessions use short lived JWTs in HttpOnly, SameSite=Lax cookies; the
  CSRF token uses a readable SameSite=Strict cookie. Production cookies require
  HTTPS and set `Secure`.
- Bearer tokens are supported for API clients. JWT access tokens are not
  immediately revocable; keep the lifetime short and continue resolving the
  subject, active state, and role from the database on protected requests.
- Administrator authorization uses the current database role. Never use the
  JWT role claim as the sole authorization decision.
- Registration always creates staff accounts. Create the initial administrator
  through the protected `create_admin.py` CLI.

## Browser request protections

- Login and registration require same-origin evidence. Cookie-authenticated
  state changes require same-origin evidence and a matching CSRF cookie and
  `X-CSRF-Token` header.
- Bearer-token API clients do not require the cookie CSRF token. Do not store
  bearer tokens in localStorage without a separate threat-model review.
- `SecurityHeadersMiddleware` supplies the current response headers. A strict
  Content Security Policy is not enabled because inline scripts/styles and
  current page behavior must first be migrated and verified against a policy.
- The icon renderer is served locally from `static/js/icons.js`; the pages do
  not depend on an unpinned icon CDN or remote web fonts.

## Database configuration and migrations

- `DATABASE_URL` is read through `config.settings`. Development and tests can
  use SQLite; production must explicitly configure PostgreSQL. A production
  SQLite URL, missing URL, malformed URL, or unsupported PostgreSQL driver fails
  configuration validation. Bare PostgreSQL URLs use the installed psycopg v3
  driver.
- Startup checks runtime settings, shared Redis availability when configured,
  and the current Alembic revision before serving traffic. It never creates or
  upgrades application tables during startup.
- Alembic requires an explicit `DATABASE_URL`. Repository SQLite files and the
  protected `agencyforge.db` are refused. Non-temporary migration targets need
  the explicit `ALLOW_NON_TMP_MIGRATIONS=1` operator setting.
- `database.adopt_legacy` adopts a separately backed up SQLite copy. It checks
  required legacy tables/columns before stamping, applies later migrations,
  checks schema consistency, and compares application row counts. It does not
  modify the backup or the protected repository database.
- SQLite baseline adoption is not SQLite-to-PostgreSQL data transfer. The app
  does not currently provide a SQLite-to-PostgreSQL transfer tool.

## Rate limits, Redis, and proxies

- Production requires shared Redis for rate limiting and AI usage budgets.
  Redis must be private, authenticated, encrypted in transit where supported,
  and restricted to the application network. Use separate credentials and a
  separate Redis deployment/database for CI and disposable integration tests.
- Request limits use distinct policy namespaces for authentication, public
  writes, AI scoping, ordinary APIs, administration, and readiness. Static files
  do not consume API budgets and receive browser caching headers. `/health` is
  process liveness; `/ready` is rate limited and briefly caches dependency
  checks.
- Failed login attempts have a shared, normalized-account HMAC counter in
  addition to the authentication IP budget. Counters expire; progressive delay
  and short throttling replace permanent account lockouts. A successful login
  clears the corresponding account failure counter.
- Redis fixed-window counts and retry intervals are computed in one Lua
  operation using Redis server time. Key retention TTL is longer than the
  client-facing retry interval.
- `X-Forwarded-For` is ignored unless the socket peer belongs to a configured
  `TRUSTED_PROXY_CIDRS` network. Configure only actual ingress addresses, and
  block direct public access to application workers.
- Configure per-account, per-session/guest, and overall daily AI request caps
  using `AI_ACCOUNT_DAILY_LIMIT`, `AI_SESSION_DAILY_LIMIT`, and
  `AI_GLOBAL_DAILY_LIMIT`. These are request-count budgets; provider-side
  monetary limits and alerts remain necessary.

## AI scoping session rules

- Authenticated conversations store an owner user ID and allow continuation
  only for that active owner. Guest conversations return a random capability
  once; the capability hash is stored server side and the UUID by itself grants
  no access.
- Guest sessions expire after 24 hours; authenticated sessions expire after 30
  days. The inquiry page keeps the guest capability in page memory for its
  current conversation and sends it only when continuing that session.
- Provider keys must be held in a secret manager/environment injection. Do not
  log prompts, capabilities, credentials, or full provider responses. Provider
  retention and data-processing terms require a separate product review.

## Deployment checklist

Before production traffic, operators still need to demonstrate and document:

1. HTTPS termination, secure cookie behavior, and trusted proxy CIDRs.
2. Secret-manager delivery and rotation for JWT, Redis, database, and AI provider
   credentials. The signing secret must be random and at least 32 bytes.
3. PostgreSQL pooling sized for worker count, TLS settings, least privilege,
   automated backups, point-in-time recovery, and a restoration drill.
4. Redis authentication, TLS/network isolation, memory limits, persistence or
   failover policy, monitoring, and recovery behavior.
5. Alerts for failed readiness, authentication abuse, Redis/DB errors, provider
   usage, budget thresholds, and backup failures.
6. A sensitive-log review, provider spending limits, and a retention policy for
   inquiry/contact data and AI conversation history.
7. A deployment test using the real production database and Redis topology.

The current CI workflow exercises isolated SQLite migrations, real Redis, a
service-backed PostgreSQL database, and a Playwright Chromium job. CI success is
not proof that production infrastructure or recovery procedures are ready.
