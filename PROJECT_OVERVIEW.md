# E-Commerce Backend — Project Overview

In one sentence: FastAPI owns identity and sessions, Kong owns the public edge,
Django owns ecommerce business logic, PostgreSQL stores data, Redis backs Celery,
token revocation, and product caching, Celery runs background work, Stripe confirms
payments, and Prometheus + Grafana provide monitoring.

---

## Progress Status

**Pre-deployment checkpoint — Phases 0–4 and Phase 6 complete.**

### Completed

| Phase | Milestone | Date |
| --- | --- | --- |
| Phase 0 | Code quality tools, settings split, Docker stack verified | June 1, 2026 |
| Phase 1 | Security hardening: refresh tokens, rotation, logout, email verification, password reset, lockouts, rate limits | June 4, 2026 |
| Phase 2 | Observability: JSON logging, standard error schema, audit events | June 8, 2026 |
| Phase 3 | Monitoring: Prometheus metrics, Grafana dashboard, health endpoints | June 12, 2026 |
| Phase 4 | CI/CD: GitHub Actions (lint/format/test), 87 tests, Dependabot, secret scanning, Docker build | June 22, 2026 |
| Phase 6 | Redis caching: product + category cache, cache-aside pattern, signal-based invalidation | June 22, 2026 |

### In Progress

| Phase | Milestone | Status |
| --- | --- | --- |
| Phase 9 | Event-Driven Architecture: Integrated RabbitMQ, set up `pika` EventPublishers for Domain Events, and created Notification Service consumer | ✅ Complete |

### Paused

- Cloud deployment (Railway / AWS) — Phase 5. (Paused due to directory name parsing issue in Railway build daemon).

### Still Open

- Production-grade secret injection for Kong JWT credentials.
- Remaining ruff linting issues (~30, mostly line length).
- Integration tests covering Kong + Django + FastAPI + Stripe end-to-end.
- Multi-device session model (currently one active refresh token per user).
- Decision on whether `/admin/`, `/static/`, and `/api/users/` should be exposed through Kong.
- Optional cleanup of legacy compatibility routes and a few error-response rough edges.

---

## High-Level Architecture

```text
Client / API Tester / Frontend
      |
      v
Kong API Gateway  (http://127.0.0.1:8080)
      |
      |-- /api/auth/*            -> FastAPI Identity Service :8001
      |-- /api/products/*        -> Django Order & Catalog :8000  [Redis cached]
      |-- /api/orders/webhook/*  -> Django Stripe webhook :8000   [public, Stripe sig]
      |-- /api/orders/*          -> Django Orders API :8000       [Kong JWT]
      |-- /orders/*              -> Kong rewrite to /api/orders/* [Kong JWT, legacy]
      |-- /api/token/*           -> Django SimpleJWT compatibility [public]
              |
              v
        PostgreSQL 15  +  Redis 7  +  RabbitMQ 3.13
              |                         |
              v                         v
        Celery Worker / Beat     Event Consumers (TBD)
              |
              v
        Prometheus / Grafana
```

Kong is the active gateway. The older Nginx configuration is retained but not used.

---

## Runtime Services

| Service | Container | Role |
| --- | --- | --- |
| `db` | `ecom_postgres` | PostgreSQL 15 database |
| `redis` | `ecom_redis` | Celery result backend, token blacklist, product/category cache |
| `rabbitmq` | `ecom_rabbitmq` | Celery broker and Domain Event Exchange (pika) |
| `identity_service` | `ecom_identity` | FastAPI identity/auth service |
| `order-service` | `ecom_django` | Django catalog, orders, Stripe, admin, monitoring |
| `order_worker` | `ecom_worker` | Celery worker |
| `order_beat` | `ecom_beat` | Celery beat scheduler |
| `gateway` | `ecom_gateway` | Kong public API gateway |

Startup order:

```text
1. PostgreSQL and Redis start.
2. Health checks confirm both are ready.
3. Django, Celery worker, Celery beat, and FastAPI start.
4. Kong starts and exposes host port 8080.
5. Client traffic reaches backend services only through Kong.
```

---

## Gateway

Files:

```text
docker-compose.yml
gateway/kong.yml
gateway/kong.template.yml
Makefile
```

Kong runs in DB-less/declarative mode:

```text
KONG_DATABASE=off
KONG_DECLARATIVE_CONFIG=/usr/local/kong/kong.yml
KONG_ADMIN_LISTEN=off
```

### Route Map

| Route | Backend | Auth |
| --- | --- | --- |
| `/api/auth/*` | FastAPI identity service | Public |
| `/api/products/*` | Django catalog (Redis cached) | Public |
| `/api/orders/webhook` | Django Stripe webhook | Stripe signature (verified inside Django) |
| `/api/orders/*` | Django orders API | Kong JWT |
| `/orders/*` | Rewritten to `/api/orders/*` | Kong JWT |
| `/api/token/*` | Django SimpleJWT compatibility | Public |

### Kong Plugins

**jwt** — Verifies `exp` on protected order and legacy checkout routes.

```text
Consumer username: identity-service
JWT credential key: ecom_identity_v1
JWT algorithm: HS256
```

**rate-limiting** — Fixed-window per route:

```text
Auth / token:        5/sec,  100/min,    1,000/hour
Orders / checkout:   3/sec,   60/min,    5,000/hour
Products:           20/sec,                50,000/hour
Stripe webhook:     10/sec,                10,000/hour
```

**request-size-limiting**:

```text
Auth / token / products / orders / legacy checkout: 1 MB
Stripe webhook: 2 MB
```

---

## Identity Service

```text
Identity Service/
  FastAPI + SQLAlchemy + PostgreSQL + passlib/bcrypt + python-jose + Redis
```

### Important Files

```text
main.py       — Routes, Redis blacklist checks, lockout logic, shadow-user sync
models.py     — SQLAlchemy identity_users table
schemas.py    — Pydantic request/response schemas, password validators
auth_utils.py — Password hashing, JWT creation, refresh-token generation
database.py   — SQLAlchemy engine/session setup
```

### Identity Table

```text
identity_users
  id
  email
  hashed_password
  is_active
  refresh_token
  refresh_token_expiry
  email_verified
  email_verification_token
  email_verification_expiry
  password_reset_token
  password_reset_expiry
```

### Password Policy

```text
Minimum length: 12
Must include: uppercase, lowercase, digit, and special character
```

### Token Behavior

**Access token:**

```text
Algorithm: HS256
Lifetime: 15 minutes
Claims: sub, user_id, exp, iss
Issuer: ecom_identity_v1
```

**Refresh token:**

```text
Secure random hex.
Stored on the identity user row.
Expires after 7 days.
Rotated on /refresh — old token blacklisted in Redis until original expiry.
Logout blacklists the active refresh token and clears it from the user row.
```

### Failed-Login Protection

```text
Email lockout: 5 failed attempts -> locked for 15 minutes
IP lockout:   20 failed attempts -> locked for 15 minutes
Progressive delay: starts at attempt 3 with a 2-second delay
All counters and lockout keys stored in Redis
```

### Redis Key Patterns

```text
auth:failed:email:<email>
auth:lockout:email:<email>
auth:failed:ip:<ip>
auth:lockout:ip:<ip>
blacklist:token:<refresh_token>
```

---

## Identity Flows

### Registration

```text
POST /api/auth/register

1. Client sends email + password through Kong.
2. FastAPI validates password strength.
3. FastAPI checks whether email already exists.
4. FastAPI hashes the password.
5. FastAPI creates an inactive identity user.
6. FastAPI creates an email verification token.
7. FastAPI logs a simulated verification URL.
8. FastAPI calls Django internal sync endpoint with is_active=false.
9. Django creates/updates the inactive shadow user.
```

### Email Verification

```text
GET /api/auth/verify-email/<token>

1. FastAPI finds identity user by verification token.
2. FastAPI rejects missing or expired tokens.
3. FastAPI marks email_verified=true and is_active=true.
4. FastAPI clears the verification token.
5. FastAPI syncs the Django shadow user with is_active=true.
```

### Login

```text
POST /api/auth/login

1. FastAPI checks IP and email lockout state.
2. FastAPI verifies email/password without leaking which part failed.
3. Failed attempts increment Redis counters.
4. Repeated failures trigger progressive delay or lockout.
5. Unverified email addresses are rejected.
6. Successful login clears failed-attempt state.
7. FastAPI returns an access token and refresh token.
```

### Refresh

```text
POST /api/auth/refresh

1. FastAPI checks whether the refresh token is blacklisted in Redis.
2. FastAPI finds the user with the current refresh token.
3. FastAPI rejects missing, expired, invalid, or blacklisted tokens.
4. FastAPI creates a new access token and new refresh token.
5. FastAPI blacklists the old refresh token until its original expiry.
6. FastAPI stores the new refresh token and expiry.
```

### Logout

```text
POST /api/auth/logout

1. FastAPI finds the user by refresh token.
2. FastAPI blacklists the refresh token in Redis until remaining expiry.
3. FastAPI clears refresh_token and refresh_token_expiry from the user row.
```

### Password Reset

```text
POST /api/auth/forgot-password
POST /api/auth/reset-password

1. Forgot-password always returns a generic success message.
2. Existing users receive a simulated reset URL in logs.
3. Reset-password validates the token and new password strength.
4. FastAPI updates the password hash.
5. Any active refresh token is blacklisted and cleared.
6. Reset token and expiry are cleared.
```

---

## Order & Catalog Service

```text
Order & Catalog Service/
  Django + Django REST Framework + PostgreSQL + Celery + Redis + Stripe + WhiteNoise
```

### Important Apps

```text
users/     — Custom email-based Django user and optional local registration
products/  — Category and product catalog (Redis cached)
orders/    — Order creation, order items, internal user sync, Stripe checkout, webhook
config/    — Settings, URLs, Celery config, authentication, exception handling
```

### Django Settings

```text
config/settings/base.py         — Shared: installed apps, middleware, DRF, Celery, Stripe, JSON logging
config/settings/development.py  — DEBUG=True, SQLite fallback for collectstatic, verbose logging
config/settings/production.py   — DEBUG=False, validate_required_env_vars(), SSL/HSTS/cookie hardening
config/env_validator.py         — Validates production env vars; can check Stripe key prefixes
```

### Django Authentication Boundary

File: `Order & Catalog Service/config/authentication.py`

DRF uses `config.authentication.KongJWTAuthentication`:

```text
1. If Kong-injected X-User-Email exists, Django gets or creates that user.
2. Otherwise Django reads the Bearer token.
3. Django requires X-Consumer-Username=identity-service as proof Kong already verified the token.
4. Django decodes non-sensitive claims without re-verifying the signature.
5. Django maps the email claim to request.user.
```

Kong is the security boundary. Protected order requests should enter Django only after Kong JWT verification.

---

## Catalog Flow

### Models

```text
Category       — name, description, is_active, created_at
Product        — category, name, description, price, stock, is_active, created_at, updated_at
```

### Routes

```text
GET /api/products/categories/
GET /api/products/categories/<id>/
GET /api/products/items/
GET /api/products/items/<id>/
```

### Caching

Products and categories are cached in Redis using the cache-aside pattern:

```text
Cache hit:  return from Redis.
Cache miss: query PostgreSQL, write result to Redis, return.

Product list TTL:  5 minutes
Category list TTL: 10 minutes

Invalidation: Django signals (post_save, post_delete) on Product and Category
clear the relevant cache keys on any save or delete.
```

---

## Order Flow

### Models

```text
Order       — user, status (pending/paid/shipped/delivered/cancelled), created_at, updated_at
OrderItem   — order, product, price (snapshot), quantity
```

### Create Order Flow

```text
POST /api/orders/

1. Client sends Bearer token to /api/orders/.
2. Kong validates JWT and forwards the request.
3. Django maps the Kong-verified identity to request.user.
4. OrderSerializer opens transaction.atomic().
5. Django creates the parent Order for request.user.
6. For each item, Django re-queries Product with select_for_update().
7. Product row is locked.
8. Stock is checked.
9. Insufficient stock raises ValidationError and rolls back.
10. Available stock is deducted.
11. OrderItem is created with price snapshot.
12. After transaction commit, Celery task is queued.
13. API returns the created order.
```

### Order List / Retrieve

```text
OrderViewSet.get_queryset() filters by request.user.
Users can only see their own orders.
```

---

## Payment Flow

### Checkout

```text
POST /api/orders/<order_id>/create-checkout-session/

1. Kong validates JWT.
2. Django resolves the order through the current user's queryset.
3. Django rejects checkout unless order.status is pending.
4. Django converts OrderItems to Stripe line items.
5. Django creates a Stripe Checkout Session.
6. Stripe receives client_reference_id = order.id.
7. Django returns checkout_url.
```

Legacy compatibility: `POST /orders/<order_id>/create-checkout-session/`

### Stripe Webhook

```text
POST /api/orders/webhook/

1. Stripe calls the public webhook route through Kong.
2. Kong does not require JWT on this route.
3. Django reads the raw body and Stripe-Signature header.
4. Django verifies the signature with STRIPE_WEBHOOK_SECRET.
5. checkout.session.completed marks pending orders as paid.
6. payment_intent.payment_failed is logged.
7. Django returns HTTP 200 for handled events.
```

---

## Background Task Flow

File: `orders/tasks.py`, `config/celery.py`

```text
Task: orders.tasks.fulfill_and_send_invoice_task(order_id)

1. Order creation commits successfully.
2. transaction.on_commit() queues the Celery task.
3. Redis stores the task message.
4. Celery worker fetches the order.
5. Worker simulates invoice generation and email dispatch.
6. Worker leaves payment status unchanged.
```

Payment lifecycle ownership is clean: Celery handles side effects, Stripe webhook handles `pending → paid`.

---

## Observability

### Structured Logging

Both services emit JSON-structured logs to stdout using `python-json-logger`.

Log events captured:

```text
Identity Service: registration, login success/failure, password reset, email verification,
                  lockouts, token rotation, logout.
Django Service:   order creation, stock changes, payment events, Stripe webhook events,
                  admin actions.
```

### Standard Error Schema

All API errors follow:

```json
{
  "error_id": "ERR_CODE",
  "message": "Human-readable description",
  "timestamp": "ISO 8601"
}
```

A global DRF exception handler in Django ensures all unhandled exceptions produce this shape.

### Health Endpoints

```text
GET /health  (Django)   — Checks PostgreSQL and Redis connectivity.
GET /health  (FastAPI)  — Checks PostgreSQL connectivity.
```

### Prometheus Metrics

Collected via `prometheus-client` in both services:

```text
API request counts and response times (histogram by route/method/status).
4xx and 5xx error rate counters.
```

### Grafana

- Backend dashboard: response times, error rates, requests/sec.

---

## Testing

### Coverage Summary

| Suite | Scope | Count |
| --- | --- | --- |
| Identity Service | Registration, email verification, login, password reset, refresh rotation, logout | 44 tests |
| Django Service | Order creation, stock validation, price snapshots, ownership isolation, error shape, middleware config | 43 tests |
| **Total** | | **87 tests** |

### Running Tests

```bash
# Run Django tests
docker-compose exec order-service pytest

# Run gateway verification
python gateway_test.py

# Quality tools
ruff check .
black --check .
isort --check-only .
mypy .
```

---

## CI/CD Pipeline

File: `.github/workflows/`

GitHub Actions runs on every push to `main`:

| Job | Tool | Status |
| --- | --- | --- |
| Lint | `ruff check` | ✅ |
| Format | `black --check` | ✅ |
| Import sort | `isort --check-only` | ✅ |
| Tests | `pytest` (both services) | ✅ |
| Docker build | `docker build` validation | ✅ |

Security automation:

- **Dependabot** — automated dependency updates.
- **GitGuardian / detect-secrets** — secret detection in commits and git history.

---

## Redis Caching

Cache-aside pattern implemented for the product catalog:

```text
Product list:   5-minute TTL   key: products:list
Category list: 10-minute TTL   key: categories:list
```

Invalidation uses Django `post_save` and `post_delete` signals — any admin save or delete
immediately clears the relevant cache key, ensuring the next request always fetches fresh data.

---

## Database Design

### Tables

```text
identity_users       — FastAPI-owned, password/session source of truth
users_customuser     — Django shadow users (email + activation status)
products_category    — Product categories
products_product     — Products with stock and pricing
orders_order         — Order lifecycle record
orders_orderitem     — Per-product order line with price snapshot
```

### Relationships

```text
Identity User      — Real auth/password/session record owned by FastAPI
Django CustomUser  — Shadow user referenced by Django request.user and order ownership

Category    → has many Products
Product     → belongs to Category, has many OrderItems, stores current stock and price
Order       → belongs to a Django CustomUser, has many OrderItems, tracks lifecycle status
OrderItem   → belongs to an Order, belongs to a Product, stores price snapshot and quantity
```

---

## Environment Variables

```text
SECRET_KEY              — Django internal cryptographic secret
JWT_SECRET              — HS256 signing secret shared between FastAPI and Kong JWT credentials
INTERNAL_CLUSTER_SECRET — Private service-to-service secret for FastAPI → Django shadow-user sync
REDIS_URL               — FastAPI Redis connection for blacklist and lockout state
STRIPE_PUBLIC_KEY       — Stripe publishable key
STRIPE_SECRET_KEY       — Stripe secret key
STRIPE_WEBHOOK_SECRET   — Stripe webhook signature secret
POSTGRES_DB / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_HOST / POSTGRES_PORT
DATABASE_URL            — Constructed PostgreSQL DSN for Django and FastAPI
ALLOWED_HOSTS           — Django allowed host list
DEBUG                   — Django debug mode flag
```

---

## Current Request Maps

### Registration

```text
Client
  -> Kong /api/auth/register
  -> FastAPI /register
  -> PostgreSQL identity_users
  -> Django /api/orders/users/sync/
  -> PostgreSQL users_customuser
```

### Login

```text
Client
  -> Kong /api/auth/login
  -> FastAPI /login
  -> Redis lockout checks
  -> FastAPI verifies password
  -> FastAPI returns access + refresh tokens
```

### Browse Products

```text
Client
  -> Kong /api/products/items/
  -> Django ProductViewSet
  -> Redis cache (hit: return immediately, miss: query PostgreSQL, populate cache)
  -> Response
```

### Create Order

```text
Client + Bearer token
  -> Kong /api/orders/
  -> Kong JWT plugin verifies token
  -> Django KongJWTAuthentication
  -> OrderSerializer transaction.atomic()
  -> Product select_for_update() row locks
  -> Stock check and deduction
  -> OrderItem price snapshot
  -> transaction.on_commit() -> Celery task
  -> Response
```

### Checkout and Webhook

```text
Client + Bearer token
  -> Kong /api/orders/<id>/create-checkout-session/
  -> Django creates Stripe Checkout Session
  -> Stripe hosted payment page
  -> Stripe POST /api/orders/webhook/
  -> Django verifies Stripe-Signature
  -> Order marked paid
```

---

## Responsibility Map

```text
Kong owns:
  Public routing and route-specific rate limiting.
  Request-size enforcement.
  JWT exp verification for protected APIs.
  Public exceptions for auth, catalog, token compatibility, and Stripe webhook.

FastAPI owns:
  Identity users and real credentials.
  Password hashing and strength policy.
  Email verification and password reset.
  JWT access-token minting (iss=ecom_identity_v1).
  Refresh-token rotation, logout, and Redis blacklisting.
  Failed-login counters, IP/email lockouts, and progressive delay.
  Shadow-user sync requests to Django.

Django owns:
  Shadow users for request.user and order ownership.
  Product catalog (with Redis caching).
  Order creation, stock integrity, and price snapshots.
  Stripe checkout session creation and webhook handling.
  Admin interface and business records.
  Prometheus metrics endpoint and health check.

Redis owns:
  Celery broker/result state.
  Refresh-token blacklist entries.
  Failed-login and lockout counters.
  Product and category cache.

RabbitMQ owns:
  Celery task queue (broker).
  Domain event publishing (via pika directly to topic exchanges).

Celery owns:
  Background invoice/email simulation after order commit.

PostgreSQL owns:
  Identity users (FastAPI).
  Django shadow users.
  Catalog, orders, and order items.

Prometheus / Grafana own:
  API metrics collection and visualization.
```

---

## Current Strengths

- Clear separation of identity and ecommerce responsibilities across services.
- Kong centralizes public routing, JWT verification, rate limiting, and payload limits.
- Public catalog and Stripe webhook routes are explicit, intentional exceptions.
- Application service ports are internal-only behind Kong.
- Internal user sync uses a dedicated secret, not public JWT material.
- Access tokens are short-lived (15 min); refresh tokens can be rotated or revoked.
- Failed-login abuse protection with progressive delay and IP/email lockouts.
- Order creation uses transactions and product row locks (`select_for_update`).
- Order item prices are historical snapshots.
- Celery work starts only after database commit (`transaction.on_commit`).
- Stripe signature verification guards all payment status changes.
- Django settings are split by environment; production validates required config at startup.
- JSON-structured logs from both services, audit events, and Prometheus metrics.
- 87 automated tests with GitHub Actions CI enforcing lint, format, and coverage.
- Redis product/category cache with signal-based invalidation.

---

## Pre-Deployment Cleanup Items

| Area | Current Note | Suggested Direction |
| --- | --- | --- |
| Kong JWT secret | `gateway/kong.yml` contains a local JWT credential secret | Generate Kong config from deployment-managed secrets; do not commit real credentials |
| Secret history | Prior development values may exist in git history | Rotate any matching real credentials before production; secret scanning is active |
| Linting | ~30 ruff issues remaining (mostly line length) | Run `ruff check --fix` for auto-fixable issues; address B008/B904 manually |
| Admin/static exposure | Django supports `/admin/` and `/static/` — not exposed through Kong | Keep intentionally internal, or add explicit locked-down Kong routes |
| Legacy checkout route | `/orders/*` exists for API spec compatibility | Prefer `/api/orders/<id>/create-checkout-session/` in new clients |
| Multi-device sessions | One active refresh token per user | Add a separate session/refresh-token table for independent device sessions |
| Error response edges | Most identity errors use the standard body | Consolidate remaining outliers and add regression tests |
| Integration tests | No automated test covers the full Kong → service chain | Add integration test suite targeting the full stack |

---

## Phase History

| Internal Phase | Description |
| --- | --- |
| Django Foundation | Custom email users, product/category models, order/order item models, serializers, viewsets, routers, tests |
| Auth and Core API | Authenticated user workflows, initial JWT behavior, user registration, user-scoped order history |
| Catalog and Business Rules | Public catalog reads, stock checks, stock deduction, price snapshots |
| Async Processing | Redis and Celery; post-order invoice/email simulation via `transaction.on_commit()` |
| Stripe Payments | Checkout Session creation, ownership checks, pending-only validation, webhook signature verification |
| Docker Runtime | Dockerfiles and `docker-compose.yml` for all services |
| Microservice Split | Identity moved to FastAPI; shadow-user pattern introduced |
| Internal Sync | FastAPI → Django shadow-user sync via `INTERNAL_CLUSTER_SECRET` |
| Kong Migration | DB-less Kong replaces Nginx; public/protected route split |
| JWT Boundary Alignment | FastAPI `iss=ecom_identity_v1`, Kong credential match, Django KongJWTAuthentication |
| Gateway Security | Route-specific rate limits and request-size limits |
| Settings and Env Cleanup | base/development/production split; production env validation |
| Identity Security Hardening | Refresh rotation, logout, Redis blacklist, email verification, password reset, lockouts, progressive delay |
| Observability | JSON logging, standard error schema, audit events |
| Monitoring | Prometheus metrics, Grafana dashboard, health endpoints |
| CI/CD | GitHub Actions pipeline, 70-test suite, Dependabot, secret scanning, Docker build |
| Redis Caching | Product/category cache-aside with signal-based invalidation |


---

# Complete Codebase Context for LLMs

This section contains the actual code and business logic of the core files across the project, aggregated here to provide full context for further enhancements.

## File: Identity Service/main.py

`python
import asyncio
import logging
import secrets
import sys
from datetime import datetime, timedelta

import auth_utils
import httpx

# Import your local modules
import models
import redis
import schemas
from database import engine, get_db
from decouple import config  # 🔐 Swapped os.getenv for decouple
from fastapi import Depends, FastAPI, HTTPException, Request, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pythonjsonlogger import jsonlogger
from sqlalchemy.orm import Session
from starlette.responses import Response

# Create the database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Identity Service")


@app.middleware("http")
async def track_requests(request: Request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    return response


# Initialize Redis client (falls back to localhost for local development)
redis_client = redis.from_url(
    config("REDIS_URL", default="redis://localhost:6379/0"), decode_responses=True
)


# MUST include /orders/ in the path now
ORDER_SERVICE_SYNC_URL = config(
    "ORDER_SERVICE_SYNC_URL",
    default="http://order-service:8000/api/orders/users/sync/",
)


# --- STRUCTURED JSON LOGGING SETUP ---
def setup_logging() -> None:
    """
    Configure root logger to emit JSON lines to stdout.
    Every log record will include: timestamp, level, message,
    logger name, and any extra fields passed at call time.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


setup_logging()

logger = logging.getLogger("identity_service")
audit_logger = logging.getLogger("identity_service.audit")

# --- PROMETHEUS METRICS ---
REQUEST_COUNT = Counter(
    "identity_requests_total",
    "Total number of requests to the identity service",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "identity_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)

AUTH_LOGIN_COUNTER = Counter(
    "identity_auth_logins_total",
    "Total login attempts",
    ["result"],  # success or failure
)


def error_response(code: str, message: str, status_code: int) -> HTTPException:
    """
    Returns a standardised HTTPException with a consistent error body.
    Use this everywhere instead of raising HTTPException directly.

    Shape: {"error": "ERROR_CODE", "message": "...", "timestamp": "..."}
    """
    return HTTPException(
        status_code=status_code,
        detail={
            "error": code,
            "message": message,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


# --- FAILED AUTH TRACKING CONFIGURATION ---
# Email lockout: 5 failures on one email → locked for 15 min
# IP lockout: 20 failures from one IP → locked for 15 min
# Progressive delay: kicks in at attempt 3, adds 2s pause before responding
#
# Redis key schema:
#   auth:failed:email:<email>  → attempt count
#   auth:lockout:email:<email> → "locked"
#   auth:failed:ip:<ip>        → attempt count
#   auth:lockout:ip:<ip>       → "locked"

MAX_ATTEMPTS_EMAIL = 5
MAX_ATTEMPTS_IP = 20
WARN_THRESHOLD = 3
LOCKOUT_SECONDS = 900  # 15 minutes
PROGRESSIVE_DELAY_SECONDS = 2


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_lockout(identifier: str, kind: str) -> None:
    lockout_key = f"auth:lockout:{kind}:{identifier}"
    if redis_client.get(lockout_key):
        ttl = redis_client.ttl(lockout_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "TOO_MANY_ATTEMPTS",
                "message": f"Too many failed attempts. Try again in {max(ttl, 1)} seconds.",
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            headers={"Retry-After": str(max(ttl, 1))},
        )


def _record_failed_attempt(identifier: str, kind: str) -> int:
    counter_key = f"auth:failed:{kind}:{identifier}"
    lockout_key = f"auth:lockout:{kind}:{identifier}"
    max_attempts = MAX_ATTEMPTS_EMAIL if kind == "email" else MAX_ATTEMPTS_IP

    current = redis_client.incr(counter_key)
    if current == 1:
        redis_client.expire(counter_key, LOCKOUT_SECONDS)

    if current >= max_attempts:
        redis_client.setex(lockout_key, LOCKOUT_SECONDS, "locked")
        redis_client.delete(counter_key)

    return current


def _clear_failed_attempts(identifier: str, kind: str) -> None:
    redis_client.delete(f"auth:failed:{kind}:{identifier}")
    redis_client.delete(f"auth:lockout:{kind}:{identifier}")


@app.get("/")
async def read_root():
    return {"message": "Identity Service is online"}


@app.get("/health/identity")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint. Verifies DB and Redis connectivity.
    Returns 200 if all dependencies are healthy, 503 if any are down.
    """
    from fastapi.responses import JSONResponse

    health = {"status": "healthy", "services": {}}
    status_code = 200

    # Check PostgreSQL
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        health["services"]["postgres"] = "healthy"
    except Exception as e:
        health["services"]["postgres"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    # Check Redis
    try:
        redis_client.ping()
        health["services"]["redis"] = "healthy"
    except Exception as e:
        health["services"]["redis"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    return JSONResponse(content=health, status_code=status_code)


@app.get("/metrics/identity")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/db-test")
def test_db_connection(db: Session = Depends(get_db)):
    return {"status": "connected", "database": "ecom_db"}


@app.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Registers a user locally, generates an email verification token,
    and syncs an inactive 'Shadow User' to the Order Service.
    """
    # 1. Check if user already exists in FastAPI DB
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise error_response(
            "EMAIL_TAKEN", "Email already registered", status.HTTP_400_BAD_REQUEST
        )

    # 2. Hash password and save to local Identity DB as inactive
    hashed_pwd = auth_utils.hash_password(user_data.password)
    verification_token = secrets.token_urlsafe(32)
    new_user = models.User(
        email=user_data.email,
        hashed_password=hashed_pwd,
        is_active=False,
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_expiry=datetime.utcnow() + timedelta(hours=24),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Log simulated verification email URL
    verification_url = (
        f"http://localhost:8080/api/auth/verify-email/{verification_token}"
    )
    logger.info(
        "Verification email simulated",
        extra={"email": user_data.email, "verification_url": verification_url},
    )

    # 4. --- SHADOW USER SYNC (Service-to-Service) ---
    async with httpx.AsyncClient() as client:
        try:
            # 🔐 Safely load the secret using python-decouple
            cluster_secret = config(
                "INTERNAL_CLUSTER_SECRET", default="fallback_dev_only_key"
            )

            # We send the request to Django's internal sync endpoint with
            # is_active = False

            sync_response = await client.post(
                ORDER_SERVICE_SYNC_URL,
                json={"email": user_data.email, "is_active": False},
                headers={"X-Internal-Secret": cluster_secret},
                timeout=5.0,
            )

            # Log failure if sync isn't successful (don't block the user)
            logger.warning(
                "Shadow user sync failed",
                extra={
                    "status_code": sync_response.status_code,
                    "detail": sync_response.text,
                },
            )

        except Exception as e:
            logger.error("Connection to Order Service failed", extra={"error": str(e)})

    return new_user


@app.post("/login", response_model=schemas.TokenResponse)
async def login(
    user_data: schemas.UserCreate, request: Request, db: Session = Depends(get_db)
):
    """
    Authenticates user and returns a JWT access token and refresh token.
    Applies IP + email lockout and progressive delay on repeated failures.
    """
    client_ip = _get_client_ip(request)

    # 1. Pre-check lockouts before touching the DB
    _check_lockout(client_ip, "ip")
    _check_lockout(user_data.email, "email")

    # 2. Credential check
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    credential_valid = user is not None and auth_utils.verify_password(
        user_data.password, user.hashed_password
    )

    if not credential_valid:
        email_attempts = _record_failed_attempt(user_data.email, "email")
        _record_failed_attempt(client_ip, "ip")
        audit_logger.warning(
            "AUTH_LOGIN_FAILED",
            extra={
                "email": user_data.email,
                "ip": client_ip,
                "attempt": email_attempts,
            },
        )
        AUTH_LOGIN_COUNTER.labels(result="failure").inc()

        # Progressive delay before responding — slows brute force without full lockout yet
        if WARN_THRESHOLD <= email_attempts < MAX_ATTEMPTS_EMAIL:
            await asyncio.sleep(PROGRESSIVE_DELAY_SECONDS)

        # Re-check in case this attempt just triggered lockout
        _check_lockout(user_data.email, "email")
        _check_lockout(client_ip, "ip")

        # Generic message — never reveal whether the email exists
        raise error_response(
            "INVALID_CREDENTIALS",
            "Incorrect email or password",
            status.HTTP_401_UNAUTHORIZED,
        )

    # 3. Email verification gate
    if not user.email_verified:
        raise error_response(
            "EMAIL_NOT_VERIFIED",
            "Email address not verified. Please verify your email first.",
            status.HTTP_403_FORBIDDEN,
        )

    # 4. Success — clear all failed attempt state
    _clear_failed_attempts(user_data.email, "email")
    _clear_failed_attempts(client_ip, "ip")

    audit_logger.info(
        "AUTH_LOGIN_SUCCESS",
        extra={"email": user_data.email, "ip": client_ip},
    )
    AUTH_LOGIN_COUNTER.labels(result="success").inc()

    # 5. Issue tokens
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    refresh_token = auth_utils.create_refresh_token()

    user.refresh_token = refresh_token
    user.refresh_token_expiry = datetime.utcnow() + timedelta(days=7)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    """
    Rotates the refresh token and returns a new access + refresh token pair.
    """
    # 1. Check if the token is blacklisted in Redis
    is_blacklisted = redis_client.get(f"blacklist:token:{payload.refresh_token}")
    if is_blacklisted:
        raise error_response(
            "TOKEN_BLACKLISTED",
            "Refresh token is blacklisted",
            status.HTTP_401_UNAUTHORIZED,
        )

    # 2. Find the user with this refresh token
    user = (
        db.query(models.User)
        .filter(models.User.refresh_token == payload.refresh_token)
        .first()
    )
    if not user:
        raise error_response(
            "INVALID_TOKEN", "Invalid refresh token", status.HTTP_401_UNAUTHORIZED
        )

    # 3. Check expiration
    if not user.refresh_token_expiry or user.refresh_token_expiry < datetime.utcnow():
        # Clear expired token
        user.refresh_token = None
        user.refresh_token_expiry = None
        db.commit()
        raise error_response(
            "TOKEN_EXPIRED", "Refresh token has expired", status.HTTP_401_UNAUTHORIZED
        )

    # 4. Rotate tokens: generate new access and refresh tokens
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    new_refresh_token = auth_utils.create_refresh_token()

    # 5. Blacklist old refresh token in Redis (with TTL equal to
    # remaining expiry time, minimum 1 second)
    remaining_ttl = 0
    if user.refresh_token_expiry:
        remaining_ttl = int(
            (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
        )
    if remaining_ttl > 0:
        redis_client.setex(
            f"blacklist:token:{payload.refresh_token}", remaining_ttl, "revoked"
        )

    # 6. Save new refresh token details to db
    user.refresh_token = new_refresh_token
    user.refresh_token_expiry = datetime.utcnow() + timedelta(days=7)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@app.post("/logout")
def logout(payload: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    """
    Logs out the user and blacklists the refresh token.
    """
    # Find user by this refresh token
    user = (
        db.query(models.User)
        .filter(models.User.refresh_token == payload.refresh_token)
        .first()
    )
    if not user:
        raise error_response(
            "INVALID_TOKEN",
            "Invalid refresh token",
            status.HTTP_400_BAD_REQUEST,
        )

    # Add to Redis blacklist (with TTL equal to remaining expiry time, minimum 1 second)
    remaining_ttl = 0
    if user.refresh_token_expiry:
        remaining_ttl = int(
            (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
        )
    if remaining_ttl > 0:
        redis_client.setex(
            f"blacklist:token:{payload.refresh_token}",
            remaining_ttl,
            "logged_out",
        )

    # Clear from DB
    user.refresh_token = None
    user.refresh_token_expiry = None
    db.commit()
    audit_logger.info(
        "AUTH_LOGOUT",
        extra={"user_refresh_token_prefix": payload.refresh_token[:8]},
    )

    return {"message": "Successfully logged out"}


@app.get("/verify-email/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verifies the user's email address and activates their account.
    """
    # 1. Find user by verification token
    user = (
        db.query(models.User)
        .filter(models.User.email_verification_token == token)
        .first()
    )
    if not user:
        raise error_response(
            "INVALID_TOKEN", "Invalid verification token", status.HTTP_400_BAD_REQUEST
        )

    # 2. Check token expiry
    if (
        user.email_verification_expiry
        and user.email_verification_expiry < datetime.utcnow()
    ):
        raise error_response(
            "TOKEN_EXPIRED",
            "Verification token has expired. Please register again.",
            status.HTTP_400_BAD_REQUEST,
        )

    # 3. Mark user as verified and active
    user.email_verified = True
    user.is_active = True
    user.email_verification_token = None
    user.email_verification_expiry = None
    db.commit()

    # 4. Sync status to Django (is_active = True)
    async with httpx.AsyncClient() as client:
        try:
            cluster_secret = config(
                "INTERNAL_CLUSTER_SECRET", default="fallback_dev_only_key"
            )
            sync_response = await client.post(
                ORDER_SERVICE_SYNC_URL,
                json={"email": user.email, "is_active": True},
                headers={"X-Internal-Secret": cluster_secret},
                timeout=5.0,
            )
            if sync_response.status_code not in [200, 201]:
                logger.warning(
                    "Shadow user sync failed on verification",
                    extra={"status_code": sync_response.status_code},
                )
        except Exception as e:
            logger.error(
                "Connection to Order Service failed on verification",
                extra={"error": str(e)},
            )
    audit_logger.info(
        "AUTH_EMAIL_VERIFIED",
        extra={"email": user.email},
    )
    return {"message": "Email verified successfully! Your account is now active."}


@app.post("/forgot-password")
def forgot_password(
    payload: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)
):
    """
    Generates a secure password reset token and prints the simulated reset link.
    """
    # 1. Look up user by email
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    # 2. Return HTTP 200 generic message if not found to prevent user enumeration
    if not user:
        return {
            "message": (
                "If the email is registered, a password reset link has been sent."
            )
        }

    # 3. Generate token and expiry
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_expiry = datetime.utcnow() + timedelta(hours=1)
    db.commit()

    # 4. Log simulated reset email
    reset_url = f"http://localhost:8080/api/auth/reset-password?token={reset_token}"
    logger.info(
        "Password reset email simulated",
        extra={"email": payload.email, "reset_url": reset_url},
    )

    return {
        "message": "If the email is registered, a password reset link has been sent."
    }


@app.post("/reset-password")
def reset_password(
    payload: schemas.PasswordResetConfirm, db: Session = Depends(get_db)
):
    """
    Resets the user password, invalidating any active session.
    """
    # 1. Find user by reset token
    user = (
        db.query(models.User)
        .filter(models.User.password_reset_token == payload.token)
        .first()
    )
    if not user:
        raise error_response(
            "INVALID_TOKEN",
            "Invalid or expired reset token",
            status.HTTP_400_BAD_REQUEST,
        )

    # 2. Check token expiry
    if user.password_reset_expiry and user.password_reset_expiry < datetime.utcnow():
        user.password_reset_token = None
        user.password_reset_expiry = None
        db.commit()
        raise error_response(
            "TOKEN_EXPIRED", "Reset token has expired", status.HTTP_400_BAD_REQUEST
        )

    # 3. Update password
    hashed_pwd = auth_utils.hash_password(payload.new_password)
    user.hashed_password = hashed_pwd

    # 4. Invalidate/revoke current refresh token to force re-login on all devices
    if user.refresh_token:
        # Blacklist it in Redis
        remaining_ttl = 0
        if user.refresh_token_expiry:
            remaining_ttl = int(
                (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
            )
        if remaining_ttl > 0:
            redis_client.setex(
                f"blacklist:token:{user.refresh_token}",
                remaining_ttl,
                "revoked",
            )
        user.refresh_token = None
        user.refresh_token_expiry = None

    # Clear reset token and expiry
    user.password_reset_token = None
    user.password_reset_expiry = None
    db.commit()

    audit_logger.info(
        "AUTH_PASSWORD_RESET",
        extra={"token_prefix": payload.token[:8]},
    )
    return {
        "message": (
            "Password reset successfully! Please log in with your new password."
        )
    }

`

## File: Identity Service/models.py

`python
from typing import TYPE_CHECKING

from database import Base
from sqlalchemy import Boolean, Column, DateTime, Integer, String

if TYPE_CHECKING:
    from typing import Any

    # Type checking declarations for mypy
    class User(Base):
        id: Any
        email: Any
        hashed_password: Any
        is_active: Any
        refresh_token: Any
        refresh_token_expiry: Any
        email_verified: Any
        email_verification_token: Any
        email_verification_expiry: Any
        password_reset_token: Any
        password_reset_expiry: Any

else:
    # Runtime declarations for SQLAlchemy
    class User(Base):
        __tablename__ = "identity_users"

        id = Column(Integer, primary_key=True, index=True)
        email = Column(String, unique=True, index=True, nullable=False)
        hashed_password = Column(String, nullable=False)
        is_active = Column(Boolean, default=True)
        refresh_token = Column(String, unique=True, index=True, nullable=True)
        refresh_token_expiry = Column(DateTime, nullable=True)
        email_verified = Column(Boolean, default=False)
        email_verification_token = Column(
            String, unique=True, index=True, nullable=True
        )

        email_verification_expiry = Column(DateTime, nullable=True)
        password_reset_token = Column(String, unique=True, index=True, nullable=True)
        password_reset_expiry = Column(DateTime, nullable=True)

`

## File: Identity Service/schemas.py

`python
import re

from pydantic import BaseModel, EmailStr, field_validator


# This is what we expect from the user when they sign up
class UserCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters long")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character")
        return v


# This is what we send BACK to the user (notice we don't send the password back!)
class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class TokenRefreshRequest(BaseModel):
    refresh_token: str

`

## File: Identity Service/auth_utils.py

`python
import os
import secrets
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

# Setup bcrypt for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT CONFIGURATION ---
# Hard fail at startup if JWT_SECRET is missing or still set to the placeholder.
# A missing secret means every token would be signed with a known public value —
# which makes the entire auth system trivially bypassable.
_raw_secret = os.getenv("JWT_SECRET", "")

if not _raw_secret or _raw_secret == "fallback_do_not_use_in_prod":
    raise RuntimeError(
        "JWT_SECRET is not set or is still the placeholder value. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
        "and add it to your .env file."
    )

SECRET_KEY: str = _raw_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def create_access_token(data: dict) -> str:
    """
    Generates a secure JWT token signed with our shared cluster secret,
    optimized for Kong Gateway edge verification.
    """
    to_encode = data.copy()

    # 1. Enforce the standardized UTC expiration time window
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    # 🟢 THE FIX: Use a stable, clean string literal for the lookup key identifier
    to_encode.update({"iss": "ecom_identity_v1"})

    # Sign and encode using jose
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return str(encoded_jwt)


def create_refresh_token() -> str:
    """
    Generates a secure random refresh token.
    """
    return secrets.token_hex(32)

`

## File: Order & Catalog Service/config/authentication.py

`python
import jwt
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

# Reference the active CustomUser model configured in your settings
User = get_user_model()


class KongJWTAuthentication(authentication.BaseAuthentication):
    """
    Authenticate using JWT token from Authorization header.
    Supports both:
    1. X-User-Email/X-User-Id headers (from Kong request-transformer)
    2. Bearer token in Authorization header (verified by Kong, decoded by Django)
    """

    def authenticate(self, request):
        # Try 1: Read headers injected by Kong request-transformer
        email = request.META.get("HTTP_X_USER_EMAIL")
        user_id = request.META.get("HTTP_X_USER_ID")

        if email:
            # Kong already processed the JWT and added headers
            try:
                user, created = User.objects.get_or_create(
                    email=email, defaults={"id": user_id} if user_id else {}
                )
                return (user, None)
            except Exception as e:
                raise exceptions.AuthenticationFailed(f"Auth error: {str(e)}") from e

        # Try 2: Parse JWT from Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None  # No auth provided

        # 🛡️ GATEWAY VERIFICATION CHECK: Enforce that Kong validated this token.
        # Kong's JWT plugin sets X-Consumer-Username to the consumer's username
        # (identity-service) upon successful JWT verification.
        consumer_username = request.META.get("HTTP_X_CONSUMER_USERNAME")
        if not consumer_username or consumer_username != "identity-service":
            raise exceptions.AuthenticationFailed(
                "Access denied: Request must be authenticated by the Kong gateway."
            )

        try:
            # Extract token
            token = auth_header[7:]  # Remove 'Bearer ' prefix

            # Decode JWT without verification first to get claims
            # (We've already verified the signature via Kong's edge validation)
            decoded = jwt.decode(token, options={"verify_signature": False})

            email = decoded.get("sub")  # 'sub' claim contains email
            user_id = decoded.get("user_id")

            if not email:
                raise exceptions.AuthenticationFailed("No email in token")

            # Create or get user
            user, created = User.objects.get_or_create(
                email=email, defaults={"id": user_id} if user_id else {}
            )

            return (user, None)

        except jwt.DecodeError as e:
            raise exceptions.AuthenticationFailed("Invalid token format") from e
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Auth error: {str(e)}") from e

`

## File: Order & Catalog Service/config/celery.py

`python
import os

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("ecom")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

`

## File: Order & Catalog Service/products/models.py

`python
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = (
            "Categories"  # Fixes Django calling it "Categorys" in the admin panel
        )

    def __str__(self):
        return self.name


class Product(models.Model):
    # The ForeignKey links this Product to a specific Category
    category = models.ForeignKey(
        Category, related_name="products", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField(default=0)  # Prevents negative inventory
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

`

## File: Order & Catalog Service/products/views.py

`python
import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

logger = logging.getLogger("products")

PRODUCT_LIST_CACHE_KEY = "product_list_active"
CATEGORY_LIST_CACHE_KEY = "category_list_active"


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.action == "list":
            cached = cache.get(CATEGORY_LIST_CACHE_KEY)
            if cached is not None:
                logger.info("Cache HIT", extra={"key": CATEGORY_LIST_CACHE_KEY})
                return cached
            logger.info("Cache MISS", extra={"key": CATEGORY_LIST_CACHE_KEY})
            queryset = Category.objects.filter(is_active=True)
            cache.set(
                CATEGORY_LIST_CACHE_KEY,
                queryset,
                settings.CACHE_TTL_CATEGORIES,
            )
            return queryset
        return Category.objects.filter(is_active=True)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.action == "list":
            cached = cache.get(PRODUCT_LIST_CACHE_KEY)
            if cached is not None:
                logger.info("Cache HIT", extra={"key": PRODUCT_LIST_CACHE_KEY})
                return cached
            logger.info("Cache MISS", extra={"key": PRODUCT_LIST_CACHE_KEY})
            queryset = Product.objects.filter(is_active=True)
            cache.set(
                PRODUCT_LIST_CACHE_KEY,
                queryset,
                settings.CACHE_TTL_PRODUCTS,
            )
            return queryset
        return Product.objects.filter(is_active=True)

`

## File: Order & Catalog Service/products/serializers.py

`python
from rest_framework import serializers

from .models import Category, Product


# 1. DEFINE THIS FIRST
class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "category_name",
            "name",
            "description",
            "price",
            "stock",
            "is_active",
        ]


# 2. DEFINE THIS SECOND (Now it can safely reference ProductSerializer!)
class CategorySerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "description", "is_active", "products"]

`

## File: Order & Catalog Service/orders/models.py

`python
from django.conf import settings

# Create your models here.
from django.db import models
from products.models import Product


class Order(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    )

    # Links the order to the CustomUser who placed it
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="orders", on_delete=models.CASCADE
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} by {self.user.email}"

    @property
    def total_cost(self):
        # Calculates the total cost of all items in this order
        return sum(item.get_cost() for item in self.items.all())


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        Product, related_name="order_items", on_delete=models.CASCADE
    )
    # We save the price here so if the product price changes next week, past orders aren't affected!
    price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def get_cost(self):
        return self.price * self.quantity

`

## File: Order & Catalog Service/orders/views.py

`python
import logging

import stripe
from decouple import config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import OrderSerializer

# 🚨 IMPORT THE COMBINED PIPELINE BACKGROUND TASK

User = get_user_model()
logger = logging.getLogger(__name__)
audit_logger = logging.getLogger("orders.audit")

stripe.api_key = settings.STRIPE_SECRET_KEY


class UserSyncView(APIView):
    """
    Internal-only endpoint to sync users from the Identity Service.
    Ensures a 'Shadow User' exists in the Django DB for order association.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        internal_secret = request.headers.get("X-Internal-Secret")
        # expected_secret = os.getenv("SECRET_KEY")

        # 🚨 SECURE UPDATE: Enforce explicit config parsing
        # If INTERNAL_CLUSTER_SECRET is completely missing from .env, decouple throws an instant error on boot rather than failing silently!
        expected_secret = config("INTERNAL_CLUSTER_SECRET")

        if not internal_secret or internal_secret != expected_secret:
            logger.warning("🚫 Unauthorized sync attempt: Secret mismatch or missing.")
            return Response(
                {"detail": "Unauthorized internal service call"},
                status=status.HTTP_403_FORBIDDEN,
            )

        email = request.data.get("email")
        is_active = request.data.get("is_active", True)
        if not email:
            return Response(
                {"detail": "Email missing"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                user, created = User.objects.get_or_create(email=email)

                user.is_active = is_active
                if created:
                    user.set_unusable_password()
                user.save()

                if created:
                    logger.info(
                        "✅ Created NEW Shadow User: %s (ID: %d, Active: %s)",
                        email,
                        user.id,
                        is_active,
                    )
                else:
                    logger.info(
                        "ℹ️ Synced existing Shadow User: %s (ID: %d, Active: %s)",
                        email,
                        user.id,
                        is_active,
                    )

            current_count = User.objects.count()
            logger.info(f"📊 Django Internal User Count: {current_count}")

            return Response(
                {
                    "message": "User sync successful",
                    "created": created,
                    "id": user.id,
                    "current_db_count": current_count,
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"❌ Critical Error during User Sync for {email}: {str(e)}")
            return Response(
                {"detail": "Internal database error during sync"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class OrderViewSet(viewsets.ModelViewSet):
    """
    Standard API for managing orders. Includes automated background
    fulfillment queues and a custom action to initiate Stripe Checkout.
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by("-created_at")

    # 🚨 HOOKING INTO ORDER CREATION TO TRIGGER ASYNC PROCESSING
    def perform_create(self, serializer):
        """
        Overrides the standard model save process.
        Saves the database entry and handshakes off to Celery instantly.
        """
        # 1. Save the record to the database (Status defaults to 'pending')
        order = serializer.save()
        logger.info(
            "Order created",
            extra={"order_id": order.id, "user_id": self.request.user.id},
        )
        audit_logger.info(
            "ORDER_CREATED",
            extra={"order_id": order.id, "user_id": self.request.user.id},
        )

        # # 2. Fire the combined worker pipeline entirely out-of-process
        # fulfill_and_send_invoice_task.delay(order.id)

    @action(detail=True, methods=["post"], url_path="create-checkout-session")
    def create_checkout_session(self, request, pk=None):
        order = self.get_object()

        # 1. Validation Guard
        if order.status != "pending":
            logger.warning(
                f"⚠️ User {request.user.id} attempted to pay for Order {order.id} with status: {order.status}"
            )
            return Response(
                {"error": f"Order cannot be paid. Current status is {order.status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Construct Stripe Line Items
        line_items = []
        for item in order.items.all():
            line_items.append(
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": item.product.name,
                        },
                        "unit_amount": int(
                            item.price * 100
                        ),  # Converts dollar integers to cents
                    },
                    "quantity": item.quantity,
                }
            )

        try:
            # 3. Create Clean Stripe Session
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=request.build_absolute_uri("/api/orders/?success=true"),
                cancel_url=request.build_absolute_uri("/api/orders/?canceled=true"),
                client_reference_id=str(order.id),
            )

            logger.info(f"💳 Stripe Session created for Order {order.id}")
            return Response({"checkout_url": checkout_session.url})

        except Exception as e:
            logger.error(f"❌ Stripe Session Creation Error: {str(e)}")
            return Response(
                {"error": "Failed to connect to Payment Gateway"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# --- WEBHOOK HANDLING ---
@csrf_exempt
def stripe_webhook(request):
    """
    Stripe Webhook listener.
    Verifies cryptographic signatures and updates order status.
    """
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    event = None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("❌ Webhook Error: Invalid payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"❌ Webhook Error: Signature Verification Failed - {e}")
        return HttpResponse(status=400)

    # Process Business Logic
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("client_reference_id")

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                if order.status == "pending":
                    order.status = "paid"
                    order.save()
                    logger.info(f"✅ WEBHOOK SUCCESS: Order {order_id} marked as PAID.")
                    audit_logger.info(
                        "PAYMENT_ORDER_PAID",
                        extra={"order_id": order_id},
                    )
                else:
                    logger.info(
                        f"ℹ️ Webhook received for Order {order_id}, but status was already {order.status}"
                    )
            except Order.DoesNotExist:
                logger.error(f"❌ WEBHOOK DATABASE ERROR: Order {order_id} not found.")
        else:
            logger.warning(
                "⚠️ Webhook received a session without a client_reference_id."
            )

    elif event["type"] == "payment_intent.payment_failed":
        session = event["data"]["object"]
        logger.warning(
            f"🚨 Payment Failed event received for Session {session.get('id')}"
        )
        audit_logger.warning(
            "PAYMENT_FAILED",
            extra={"stripe_session_id": session.get("id")},
        )

    return HttpResponse(status=200)

`

## File: Order & Catalog Service/orders/serializers.py

`python
from django.db import transaction
from products.models import Product
from rest_framework import serializers

from .models import Order, OrderItem
from .tasks import fulfill_and_send_invoice_task


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    price = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ["product", "product_name", "quantity", "price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    total_cost = serializers.ReadOnlyField()
    status = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ["id", "status", "created_at", "total_cost", "items"]

    def create(self, validated_data):
        items_data = validated_data.pop("items")

        # 📌 1. Open an atomic database transaction context block
        with transaction.atomic():
            # Create the parent order shell linked to the context request user
            order = Order.objects.create(
                user=self.context["request"].user, **validated_data
            )

            for item_data in items_data:
                product_instance = item_data["product"]
                quantity = item_data["quantity"]

                # 📌 2. RE-QUERY AND LOCK THE ROW AT DATABASE LEVEL
                # This explicitly blocks concurrency race conditions
                product = Product.objects.select_for_update().get(
                    id=product_instance.id
                )

                # 📌 3. Atomic Evaluation & Deduct Combined
                if product.stock < quantity:
                    raise serializers.ValidationError(
                        f"Not enough stock for {product.name}. Only {product.stock} left."
                    )

                # Deduct inventory securely
                product.stock -= quantity
                product.save()

                # Lock in the line-item snapshot invoice metadata
                OrderItem.objects.create(
                    order=order, product=product, price=product.price, quantity=quantity
                )

        # 📌 4. BACKGROUND TASKS (Triggered only AFTER transaction safely commits)
        # We pass it to Celery. .delay() drops a message straight into Redis!
        transaction.on_commit(lambda: fulfill_and_send_invoice_task.delay(order.id))

        return order

`

## File: Order & Catalog Service/orders/tasks.py

`python
import logging
import time

from celery import shared_task

from .models import Order

logger = logging.getLogger(__name__)


@shared_task(name="orders.tasks.fulfill_and_send_invoice_task")
def fulfill_and_send_invoice_task(order_id):
    """
    Background worker process: Takes an order ID, advances the pending state,
    and simulates heavy out-of-process operations (PDF generation & email dispatch).
    """
    print(f"\n[CELERY] Starting background processing for Order {order_id}...")

    try:
        # Fetch the order from the database inside the worker process
        order = Order.objects.get(id=order_id)

        # 🚨 FIX: Do not change order status to 'completed' here.
        # Fulfilling the order should keep it as 'pending' until Stripe payment changes it to 'paid'.
        # 'completed' is also not a valid status in Order.STATUS_CHOICES.
        print(
            f"[CELERY] INFO: Processing invoice for Order {order_id} (Current status: {order.status})."
        )

        # --- HEAVY ASYNC PROCESSING WORKLOAD ---
        print(
            "[CELERY] Simulating heavy 5-second invoice generation and email dispatch..."
        )
        time.sleep(5)

        # Pull the email safely from the authenticated user relation
        user_email = order.user.email if order.user else "unknown_user@test.com"
        print(f"[CELERY] SUCCESS: PDF Invoice generated for Order {order.id}!")
        print(f"[CELERY] SUCCESS: Email sent cleanly to {user_email}!")

        return f"Pipeline complete for Order {order_id}"

    except Order.DoesNotExist:
        print(f"[CELERY] ERROR: Order {order_id} not found in the database.")
        return f"Order {order_id} missing."

    except Exception as e:
        print(f"[CELERY] CRITICAL SYSTEM FAULT: {str(e)}")
        raise e

`

## File: Order & Catalog Service/users/models.py

`python
# Create your models here.
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # This hashes the password!
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)

    # Required fields for Django's admin/auth system
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"  # This tells Django to use email to log in!
    REQUIRED_FIELDS: list[str] = (
        []
    )  # Email is automatically required, so this stays empty

    def __str__(self):
        return self.email

`

## File: gateway/kong.template.yml

`yaml
_format_version: "3.0"
_transform: true

services:
  # --- IDENTITY SERVICE (FastAPI) ---
  - name: identity-service
    # Railway private network URL — resolves within the Railway project only.
    # Docker Compose equivalent: http://identity_service:8001
    url: http://identity-service.railway.internal:8001
    routes:
      - name: identity-routes
        paths:
          - /api/auth
        strip_path: true
        plugins:
          - name: rate-limiting
            config:
              second: 5
              minute: 100
              hour: 1000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 1
      - name: identity-health-route
        paths:
          - /health/identity
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 10
              policy: local
      - name: identity-metrics-route
        paths:
          - /metrics/identity
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 5
              policy: local

  # --- ORDER & CATALOG SERVICE (Django) ---
  - name: order-service
    # Railway private network URL — resolves within the Railway project only.
    # Docker Compose equivalent: http://order-service:8000
    url: http://order-service.railway.internal:8000
    routes:
      - name: order-webhook-route
        # Public webhook for Stripe callbacks (no authentication)
        paths:
          - /api/orders/webhook
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 10
              hour: 10000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 2

      - name: products-public-route
        # Public catalog route (no authentication)
        paths:
          - /api/products
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 20
              hour: 50000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 1

      - name: token-public-route
        paths:
          - /api/token
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 5
              minute: 100
              hour: 1000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 1
      - name: django-health-route
        paths:
          - /health/django
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 10
              policy: local
      - name: django-metrics-route
        paths:
          - /metrics/django
        strip_path: false
        plugins:
          - name: rate-limiting
            config:
              second: 5
              policy: local

      - name: orders-protected-route
        # Protected route for creating and retrieving orders
        paths:
          - /api/orders
        strip_path: false
        plugins:
          # 🔐 ADDED: Verify Bearer JWT tokens at the gateway level
          - name: jwt
            config:
              claims_to_verify:
                - exp
          - name: rate-limiting
            config:
              second: 3
              minute: 60
              hour: 5000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 1

      - name: orders-legacy-checkout-route
        # ⚡ ADDED: Support the URL structure from API Spec Ecom.yaml (/orders/{{orderId}}/create-checkout-session/)
        # Using a regex capture group to capture the remaining path segment
        paths:
          - ~/orders/(?<checkout_path>.*)
        strip_path: false
        plugins:
          # 🔐 Verify JWT token before routing
          - name: jwt
            config:
              claims_to_verify:
                - exp
          # 🔄 Rewrite path to include '/api/orders/' (e.g. /orders/1/create-checkout-session/ -> /api/orders/1/create-checkout-session/)
          - name: request-transformer
            config:
              replace:
                uri: "/api/orders/$(uri_captures['checkout_path'])"
          - name: rate-limiting
            config:
              second: 3
              minute: 60
              hour: 5000
              policy: local
          - name: request-size-limiting
            config:
              allowed_payload_size: 1

# 🔐 DECLARATIVE AUTHENTICATION CREDENTIALS
# We define our consumer identity-service and its corresponding JWT key/secret pair.
consumers:
  - username: identity-service
    jwt_secrets:
      - key: "ecom_identity_v1"
        # Production should generate this config from secret-managed deployment input.
        secret: "${KONG_JWT_SECRET}"
        algorithm: HS256

`

## File: docker-compose.yml

`yaml
version: '3.8'

services:
  # --- SHARED INFRASTRUCTURE ---
  db:
    image: postgres:15
    container_name: ecom_postgres
    environment:
      POSTGRES_DB: ecom_db
      POSTGRES_USER: ecom_user
      POSTGRES_PASSWORD: ecom_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ecom_user -d ecom_db"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: ecom_redis
    ports:
      - "6379:6379"
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "redis-cli ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    container_name: ecom_rabbitmq
    ports:
      - "5672:5672"   # AMQP protocol port (Celery/kombu connect here)
      - "15672:15672" # Management UI
    environment:
      RABBITMQ_DEFAULT_USER: ecom_user
      RABBITMQ_DEFAULT_PASS: ecom_password
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
    restart: always
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  # --- ORDER & CATALOG SERVICE (Django) ---
  order-service:
    build:
      context: "./Order & Catalog Service"
      dockerfile: Dockerfile
    container_name: ecom_django
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - "./Order & Catalog Service:/app"
      - django_static:/app/static/
    expose:
      - "8000"
    # ports:
    #   - "8000:8000"  # Expose Django's internal port 8000 to the host for direct access (optional, can be removed if only accessed via Kong)
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    restart: always

  order_worker:
    build: "./Order & Catalog Service"
    container_name: ecom_worker
    command: celery -A config worker --loglevel=info
    volumes:
      - "./Order & Catalog Service:/app"
    env_file:
      - .env
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
      - CELERY_BROKER_URL=amqp://ecom_user:ecom_password@rabbitmq:5672//
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
      rabbitmq:
        condition: service_healthy
    restart: always

  order_beat:
    build: "./Order & Catalog Service"
    container_name: ecom_beat
    command: celery -A config beat --loglevel=info
    volumes:
      - "./Order & Catalog Service:/app"
    env_file:
      - .env
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - JWT_SECRET=${JWT_SECRET}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: always

  # --- IDENTITY SERVICE (FastAPI) ---
  identity_service:
    build:
      context: "./Identity Service"
      dockerfile: Dockerfile
    container_name: ecom_identity
    expose:
      - "8001"
    volumes:
      - "./Identity Service:/app"
    env_file:
      - .env
    environment:
      - DATABASE_URL=postgresql://ecom_user:ecom_password@db:5432/ecom_db
      - JWT_SECRET=${JWT_SECRET}
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

    restart: always

  # --- KONG API GATEWAY ---
  # Replaced Nginx to support edge-level Centralized JWT Verification for free
  gateway:
    image: kong:3.4
    container_name: ecom_gateway
    environment:
      KONG_DATABASE: "off"                             # Force Kong into DB-less/Declarative mode
      KONG_DECLARATIVE_CONFIG: /usr/local/kong/kong.yml # Target mount path inside the container
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_LISTEN: "off"                         # Lock down Admin API from external access
    env_file:
      - .env
    ports:
      - "8080:8000"                                      # Proxy external port 80 requests into Kong's internal port 8000
    volumes:
      - ./gateway/kong.yml:/usr/local/kong/kong.yml:ro
    depends_on:
      - identity_service
      - order-service
    restart: always
  # --- MONITORING ---
  prometheus:
    image: prom/prometheus:v2.51.0
    container_name: ecom_prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.path=/prometheus"
      - "--storage.tsdb.retention.time=7d"
    ports:
      - "9090:9090"
    depends_on:
      - order-service
      - identity_service
    restart: always

  grafana:
    image: grafana/grafana:10.4.0
    container_name: ecom_grafana
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_USER=admin
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_USERS_ALLOW_SIGN_UP=false
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: always

volumes:
  postgres_data:
  django_static:
  prometheus_data:
  grafana_data:
  rabbitmq_data:

# PREVIOUS NGINX CONFIGURATION

#  gateway:
#    image: nginx:latest
#    container_name: ecom_gateway
#    ports:
#      - "80:80"
#    volumes:
#      - ./gateway/nginx.conf:/etc/nginx/conf.d/default.conf
#      - django_static:/app/static/:ro
#    depends_on:
#      - identity_service
#      - order-service
#    restart: always

`
