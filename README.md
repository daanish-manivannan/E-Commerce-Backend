# E-Commerce Backend Platform

A containerized, production-hardened e-commerce backend built as a microservice system.

FastAPI handles identity and sessions, Kong owns the public edge, Django REST Framework
owns ecommerce business logic, PostgreSQL stores persistent data, Redis backs Celery and
token revocation state, Celery runs background work, and Stripe confirms payments.

## Current Status

**Pre-deployment checkpoint — Phases 0–4 and Phase 6 complete.**

The platform has moved well beyond the initial Django API into a gateway-first, observability-ready
backend with hardened identity, automated CI/CD, Redis caching, and 70 automated tests.

## What Has Been Built

| Phase | Description | Status |
| --- | --- | --- |
| Phase 0 | Code quality, settings split, Docker stack | ✅ Complete — June 1, 2026 |
| Phase 1 | Security hardening (tokens, email verification, lockouts, rate limits) | ✅ Complete — June 4, 2026 |
| Phase 2 | Observability (structured JSON logs, standard error responses, audit logs) | ✅ Complete — June 8, 2026 |
| Phase 3 | Monitoring (Prometheus, Grafana, health checks) | ✅ Complete — June 12, 2026 |
| Phase 4 | CI/CD pipeline (GitHub Actions, 70 tests, Dependabot, Docker build) | ✅ Complete — June 22, 2026 |
| Phase 6 | Redis caching (product and category cache, cache-aside, signal invalidation) | ✅ Complete — June 22, 2026 |
| Phase 5 | Cloud deployment (Railway / AWS) | 🔜 Next |

## Architecture

```text
Client / REST Client / Frontend
      |
      v
Kong API Gateway
Host: http://127.0.0.1:8080
      |
      |-- /api/auth/*            -> FastAPI Identity Service :8001
      |-- /api/products/*        -> Django Order & Catalog Service :8000  (Redis cached)
      |-- /api/orders/webhook/*  -> Django Stripe Webhook :8000
      |-- /api/orders/*          -> Django Orders API :8000, JWT protected
      |-- /orders/*              -> Legacy checkout compatibility route
      |-- /api/token/*           -> Django SimpleJWT compatibility route
              |
              v
        PostgreSQL + Redis
              |
              v
        Celery Worker / Beat
              |
              v
        Prometheus + Grafana
```

## Tech Stack

| Layer | Technology |
| --- | --- |
| API Gateway | Kong 3.4, DB-less declarative config |
| Identity | FastAPI, SQLAlchemy, bcrypt/passlib, python-jose, Redis, python-decouple |
| Commerce | Django, Django REST Framework, WhiteNoise, split settings |
| Database | PostgreSQL 15 |
| Async | Redis 7, Celery worker, Celery beat |
| Caching | Redis (product & category cache, cache-aside, signal-based invalidation) |
| Payments | Stripe Checkout, Stripe webhooks |
| Auth | HS256 JWT (15-min access, 7-day refresh rotation), Redis blacklist, Kong JWT plugin |
| Observability | Structured JSON logging, standard error schema, audit log events |
| Monitoring | Prometheus metrics, Grafana dashboard, health endpoints |
| Testing | pytest, pytest-django, DRF APIClient — 70 tests (44 identity + 26 Django) |
| CI/CD | GitHub Actions (lint, format, import-sort, tests), Dependabot, GitGuardian |
| Quality | ruff, black, isort, mypy, pre-commit |
| Runtime | Docker, Docker Compose |

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `db` | `ecom_postgres` | PostgreSQL 15 for identity and commerce data |
| `redis` | `ecom_redis` | Celery broker/result backend, auth blacklist, and product cache |
| `identity_service` | `ecom_identity` | FastAPI registration, login, tokens, email verification, lockouts |
| `order-service` | `ecom_django` | Django catalog, orders, payments, admin, caching, monitoring |
| `order_worker` | `ecom_worker` | Celery background invoice/email simulation |
| `order_beat` | `ecom_beat` | Celery scheduler |
| `gateway` | `ecom_gateway` | Kong public API gateway on host port `8080` |

## Repository Guide

```text
Identity Service/
  FastAPI identity microservice.

Order & Catalog Service/
  Django ecommerce service with users, products, orders, settings, Celery,
  Stripe logic, Redis cache, and Prometheus metrics.

gateway/
  Kong declarative configuration (kong.yml, kong.template.yml).

monitoring/
  Prometheus configuration.

.github/
  GitHub Actions CI/CD workflow.

docker-compose.yml
  Full local stack orchestration.

Makefile
  Helper targets for generating/reloading Kong config.

api_tests.rest
  Manual API flow through Kong.

gateway_test.py
  Gateway behavior verification helper.

PROJECT_OVERVIEW.md
  Detailed architecture, flow diagrams, implementation notes, and cleanup items.

API Spec Ecom 2.yaml
  API specification artifact.
```

## Public Gateway Routes

Base URL: `http://127.0.0.1:8080`

| Route | Service | Auth | Purpose |
| --- | --- | --- | --- |
| `POST /api/auth/register` | FastAPI | Public | Register identity user and create inactive Django shadow user |
| `POST /api/auth/login` | FastAPI | Public | Login and receive access + refresh tokens |
| `POST /api/auth/refresh` | FastAPI | Refresh token | Rotate refresh token and receive a fresh token pair |
| `POST /api/auth/logout` | FastAPI | Refresh token | Blacklist refresh token and clear active session |
| `GET /api/auth/verify-email/<token>` | FastAPI | Public token link | Verify email and activate identity + shadow users |
| `POST /api/auth/forgot-password` | FastAPI | Public | Generate simulated password reset link |
| `POST /api/auth/reset-password` | FastAPI | Reset token | Reset password and revoke active refresh session |
| `GET /api/products/categories/` | Django | Public | List active categories (Redis cached, 10 min TTL) |
| `GET /api/products/items/` | Django | Public | List active products (Redis cached, 5 min TTL) |
| `POST /api/orders/` | Django | JWT | Create order |
| `GET /api/orders/` | Django | JWT | List current user's orders |
| `GET /api/orders/<id>/` | Django | JWT | Retrieve current user's order |
| `POST /api/orders/<id>/create-checkout-session/` | Django | JWT | Create Stripe Checkout session |
| `POST /api/orders/webhook/` | Django | Stripe signature | Receive Stripe payment events |
| `POST /orders/<id>/create-checkout-session/` | Kong rewrite → Django | JWT | Legacy checkout route compatibility |
| `POST /api/token/` | Django | Public | SimpleJWT compatibility endpoint |
| `POST /api/token/refresh/` | Django | Public | SimpleJWT compatibility endpoint |

`/admin/`, `/static/`, and `/api/users/` exist in Django but are not currently exposed through Kong.

## Gateway Controls

Kong route limits are configured in `gateway/kong.yml`.

| Route group | Rate limit | Payload limit |
| --- | --- | --- |
| `/api/auth`, `/api/token` | 5/sec, 100/min, 1,000/hour | 1 MB |
| `/api/orders`, `/orders/*` | 3/sec, 60/min, 5,000/hour | 1 MB |
| `/api/products` | 20/sec, 50,000/hour | 1 MB |
| `/api/orders/webhook` | 10/sec, 10,000/hour | 2 MB |

All limits use Kong's local fixed-window policy.

## Security Model

- **Kong** is the security boundary. It verifies JWT `exp` before protected order requests reach Django.
- **FastAPI** owns all credentials: password hashing, JWT minting, refresh rotation, logout, and lockouts.
- **Django** trusts Kong — it checks `X-Consumer-Username: identity-service` before accepting token claims.
- **Failed-login protection**: 5 failed attempts → email lockout (15 min); 20 failed attempts → IP lockout (15 min). Progressive delay starts at attempt 3.
- **Refresh tokens**: 7-day lifetime, rotated on every `/refresh` call. Old tokens are blacklisted in Redis.
- **Password policy**: minimum 12 characters with uppercase, lowercase, digit, and special character.

## Main User Flow

```text
Register → /api/auth/register
  -> FastAPI creates inactive identity user
  -> FastAPI logs simulated email verification URL
  -> FastAPI syncs inactive shadow user into Django

Verify email → /api/auth/verify-email/<token>
  -> FastAPI activates identity user and Django shadow user

Login → /api/auth/login
  -> FastAPI returns access token (15 min) + refresh token (7 days)

Browse public products → GET /api/products/items/
  -> Django serves cached product list from Redis (cache-aside, 5 min TTL)

Create order → POST /api/orders/
  -> Kong verifies JWT
  -> Django locks product rows (select_for_update) and deducts stock
  -> Celery invoice/email task starts after commit

Checkout → POST /api/orders/<id>/create-checkout-session/
  -> Django creates Stripe Checkout session

Pay → Stripe hosted page
  -> Stripe webhook marks order as paid
```

## Business Rules

- FastAPI owns real credentials, password security, JWT creation, refresh rotation, logout, and account recovery.
- Django owns ecommerce records, shadow users, catalog, order ownership, stock integrity, Stripe checkout, and Stripe webhook handling.
- Kong owns public routing, JWT verification for protected routes, fixed-window rate limits, and request-size limits.
- Redis stores Celery messages/results, refresh-token blacklist entries, failed-login counters, and product/category caches.
- Celery runs post-order invoice/email simulation **only after** the database transaction commits (`transaction.on_commit()`).
- Stripe is the source of truth for moving an order from `pending` to `paid`.

Order integrity rules:

- Product stock is checked inside `transaction.atomic()`.
- Product rows are locked with `select_for_update()` during order creation.
- Insufficient stock raises a `ValidationError` and rolls back the transaction.
- Order item prices are copied at purchase time (price snapshot).
- Celery task dispatch happens through `transaction.on_commit()`.

## Observability

- **Structured JSON logs**: Both FastAPI and Django emit JSON-formatted logs to stdout using `python-json-logger`.
- **Standard error schema**: All API errors return `{ "error_id": "ERR_CODE", "message": "...", "timestamp": "..." }`.
- **Audit events logged**: Login, logout, password changes, order creation, state changes, payment events.
- **Prometheus metrics**: API response times, status code counts, 4xx/5xx error rates.
- **Health endpoints**: `GET /health` on both Django and FastAPI (DB + Redis connectivity checks).
- **Grafana dashboard**: Response times, error rates, requests/sec.

## Testing

| Suite | Coverage | Count |
| --- | --- | --- |
| Identity Service | Registration, email verification, login, password reset, refresh rotation, logout | 44 tests |
| Django Service | Order creation, stock validation, price snapshots, ownership isolation, error shape | 26 tests |
| **Total** | | **70 tests** |

Run Django/identity tests:

```bash
docker-compose exec order-service pytest
```

Run gateway verification:

```bash
python gateway_test.py
```

Run quality tools from the repo root:

```bash
ruff check .
black --check .
isort --check-only .
mypy .
```

## CI/CD

GitHub Actions runs on every push to `main`:

- `ruff check` — linting
- `black --check` — formatting
- `isort --check-only` — import sorting
- `pytest` — full test suite across both services
- Docker build validation

Security automation:

- **Dependabot** — automated dependency updates
- **GitGuardian / detect-secrets** — secret detection in git history and commits

## Environment Variables

Create a `.env` file in the project root.

```env
DEBUG=True
SECRET_KEY=your_django_secret
JWT_SECRET=your_shared_hs256_secret
INTERNAL_CLUSTER_SECRET=your_internal_service_secret
REDIS_URL=redis://redis:6379/0

POSTGRES_DB=ecom_db
POSTGRES_USER=ecom_user
POSTGRES_PASSWORD=ecom_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

DATABASE_URL=postgresql://ecom_user:ecom_password@db:5432/ecom_db

STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

ALLOWED_HOSTS=localhost,127.0.0.1,order-service,gateway
```

Production settings in `Order & Catalog Service/config/settings/production.py`
validate all required environment variables at startup. Stripe key format validation
is also available in `config/env_validator.py`.

> **Security note:** `gateway/kong.yml` currently contains a local JWT credential secret.
> For deployment, generate Kong config from a secret manager or deployment-time input
> rather than committing real credentials.

## Run Locally

Start the full stack:

```bash
docker-compose up --build
```

Or run detached:

```bash
docker-compose up --build -d
```

Run Django migrations:

```bash
docker-compose exec order-service python manage.py migrate
```

Create a Django admin user:

```bash
docker-compose exec order-service python manage.py createsuperuser
```

Check containers:

```bash
docker-compose ps
```

Follow logs:

```bash
docker-compose logs -f gateway identity_service order-service order_worker
```

Regenerate Kong config from template and `.env`:

```bash
make kong-config
```

Regenerate config and restart only Kong:

```bash
make kong-reload
```

## API Walkthrough

Password policy requires at least 12 characters with uppercase, lowercase, digit, and special character. Example: `StrongerP@ss123`

**Register:**

```http
POST http://127.0.0.1:8080/api/auth/register
Content-Type: application/json

{
  "email": "daanish@test.com",
  "password": "StrongerP@ss123"
}
```

Copy the simulated verification URL from `identity_service` logs and call it through Kong:

```http
GET http://127.0.0.1:8080/api/auth/verify-email/<token>
```

**Login:**

```http
POST http://127.0.0.1:8080/api/auth/login
Content-Type: application/json

{
  "email": "daanish@test.com",
  "password": "StrongerP@ss123"
}
```

Response:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer"
}
```

**Refresh:**

```http
POST http://127.0.0.1:8080/api/auth/refresh
Content-Type: application/json

{ "refresh_token": "<refresh_token>" }
```

**Logout:**

```http
POST http://127.0.0.1:8080/api/auth/logout
Content-Type: application/json

{ "refresh_token": "<refresh_token>" }
```

**Browse products (cached):**

```http
GET http://127.0.0.1:8080/api/products/items/
```

**Create order:**

```http
POST http://127.0.0.1:8080/api/orders/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "items": [
    { "product": 1, "quantity": 1 }
  ]
}
```

**Create Stripe Checkout session:**

```http
POST http://127.0.0.1:8080/api/orders/<order_id>/create-checkout-session/
Authorization: Bearer <access_token>
Content-Type: application/json

{}
```

**Stripe webhook (public, Stripe signature verified inside Django):**

```http
POST http://127.0.0.1:8080/api/orders/webhook/
Stripe-Signature: <stripe_signature>
```

## Project History

The project was built incrementally across multiple engineering phases:

```text
Django monolith
  -> tested ecommerce domain model (users, products, orders, stock, price snapshots)
  -> Redis/Celery async processing (transaction.on_commit dispatch)
  -> Stripe checkout and webhook lifecycle
  -> Dockerized production-style runtime
  -> FastAPI identity microservice (shadow-user sync via INTERNAL_CLUSTER_SECRET)
  -> Kong gateway migration (public/protected route split, JWT verification)
  -> Edge rate limiting and request-size limiting per route
  -> Split Django settings (base/development/production) + env validation
  -> Refresh-token rotation, logout, email verification, password reset
  -> Failed-login lockouts (email + IP) and progressive delay
  -> Structured JSON logging, standard error responses, audit events
  -> Prometheus metrics + Grafana dashboard + health endpoints
  -> GitHub Actions CI/CD (lint, format, test) + Dependabot + secret scanning
  -> Redis caching for products and categories (cache-aside, signal invalidation)
  -> 70 automated tests (44 identity + 26 Django)
```

## Pre-Deployment Cleanup Items

| Area | Note |
| --- | --- |
| Kong JWT secret | `gateway/kong.yml` contains a local credential — use deployment-time injection for production |
| Git secret history | Prior development values may exist in git history — rotate any matching credentials |
| Admin/static exposure | `/admin/` and `/static/` are intentionally not exposed through Kong |
| Legacy checkout route | `/orders/*` exists for compatibility — prefer `/api/orders/<id>/create-checkout-session/` |
| Multi-device sessions | Currently one active refresh token per user — add session table if independent device sessions are needed |
| Linting | ~30 ruff issues remaining (mostly line length) — `ruff check --fix` handles many |
