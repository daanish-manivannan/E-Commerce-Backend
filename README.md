# E-Commerce Backend Platform

A containerized ecommerce backend built as a small microservice-style system.

The platform uses FastAPI for identity, Django REST Framework for catalog and
order logic, Kong as the public API gateway, PostgreSQL for persistent data,
Redis for Celery and token blacklist state, Celery for background work, and
Stripe for checkout/payment confirmation.

## Current Status

The project has moved beyond the initial Django API into a gateway-first backend
with separated identity and commerce services.

Implemented:

- FastAPI identity service with registration, login, email verification,
  password reset, access tokens, refresh-token rotation, logout, failed-login
  tracking, lockouts, and progressive delay.
- Django order/catalog service with public product reads, authenticated order
  creation, row-level stock locking, price snapshots, Stripe checkout, Stripe
  webhooks, admin support, JSON logging, split settings, and environment
  validation.
- Kong DB-less gateway with public route exceptions, edge JWT verification,
  route-specific fixed-window rate limits, and request-size limits.
- PostgreSQL, Redis, Django, FastAPI, Celery worker, Celery beat, and Kong wired
  together through Docker Compose.
- Internal shadow-user sync from FastAPI to Django using
  `INTERNAL_CLUSTER_SECRET`.
- Development tooling for formatting, linting, type checking, and pre-commit.

## Architecture

```text
Client / REST Client / Frontend
      |
      v
Kong API Gateway
Host: http://127.0.0.1:8080
      |
      |-- /api/auth/*            -> FastAPI Identity Service :8001
      |-- /api/products/*        -> Django Order & Catalog Service :8000
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
```

Kong replaced the earlier Nginx gateway so public routing, protected route
verification, throttling, and payload limits can be handled before requests reach
the application services.

## Tech Stack

| Layer | Technology |
| --- | --- |
| API Gateway | Kong 3.4, DB-less declarative config |
| Identity | FastAPI, SQLAlchemy, bcrypt/passlib, python-jose, Redis, python-decouple |
| Commerce | Django, Django REST Framework, WhiteNoise, split settings |
| Database | PostgreSQL 15 |
| Async | Redis 7, Celery worker, Celery beat |
| Payments | Stripe Checkout, Stripe webhooks |
| Auth | HS256 JWT access tokens, refresh-token rotation, Redis blacklist, Kong JWT plugin |
| Testing/Quality | pytest, pytest-django, DRF APIClient, ruff, black, isort, mypy, pre-commit |
| Runtime | Docker, Docker Compose |

## Services

| Service | Container | Purpose |
| --- | --- | --- |
| `db` | `ecom_postgres` | PostgreSQL database for identity and commerce data |
| `redis` | `ecom_redis` | Celery broker/result backend and auth blacklist store |
| `identity_service` | `ecom_identity` | FastAPI registration, login, tokens, account security |
| `order-service` | `ecom_django` | Django catalog, orders, payments, admin, business logic |
| `order_worker` | `ecom_worker` | Celery background invoice/email simulation |
| `order_beat` | `ecom_beat` | Celery scheduler |
| `gateway` | `ecom_gateway` | Kong public gateway on host port `8080` |

## Repository Guide

```text
Identity Service/
  FastAPI identity microservice.

Order & Catalog Service/
  Django ecommerce service with users, products, orders, settings, Celery,
  and Stripe logic.

gateway/
  Kong declarative configuration and older Nginx gateway config.

docker-compose.yml
  Full local stack orchestration.

Makefile
  Helper targets for generating/reloading Kong config.

api_tests.rest
  Manual API flow through Kong.

gateway_test.py
  Gateway behavior verification helper.

PROJECT_OVERVIEW.md
  Detailed architecture, implementation progress, and next cleanup items.

API Spec Ecom 2.yaml
  API specification artifact.
```

## Public Gateway Routes

Base URL:

```text
http://127.0.0.1:8080
```

| Route | Service | Auth | Purpose |
| --- | --- | --- | --- |
| `POST /api/auth/register` | FastAPI | Public | Register identity user and create inactive Django shadow user |
| `POST /api/auth/login` | FastAPI | Public | Login and receive access + refresh tokens |
| `POST /api/auth/refresh` | FastAPI | Refresh token | Rotate refresh token and receive a fresh token pair |
| `POST /api/auth/logout` | FastAPI | Refresh token | Blacklist refresh token and clear active session |
| `GET /api/auth/verify-email/<token>` | FastAPI | Public token link | Verify email and activate identity + shadow users |
| `POST /api/auth/forgot-password` | FastAPI | Public | Generate simulated password reset link |
| `POST /api/auth/reset-password` | FastAPI | Reset token | Reset password and revoke active refresh session |
| `GET /api/products/categories/` | Django | Public | List active categories |
| `GET /api/products/items/` | Django | Public | List active products |
| `POST /api/orders/` | Django | JWT | Create order |
| `GET /api/orders/` | Django | JWT | List current user's orders |
| `GET /api/orders/<id>/` | Django | JWT | Retrieve current user's order |
| `POST /api/orders/<id>/create-checkout-session/` | Django | JWT | Create Stripe Checkout session |
| `POST /api/orders/webhook/` | Django | Stripe signature | Receive Stripe payment events |
| `POST /orders/<id>/create-checkout-session/` | Kong rewrite -> Django | JWT | Legacy checkout route compatibility |
| `POST /api/token/` | Django | Public | SimpleJWT compatibility endpoint |
| `POST /api/token/refresh/` | Django | Public | SimpleJWT compatibility endpoint |

`/admin/`, `/static/`, and `/api/users/` exist in Django, but are not currently
exposed through Kong.

## Gateway Controls

Kong route limits are configured in `gateway/kong.yml`.

| Route group | Rate limit | Payload limit |
| --- | --- | --- |
| `/api/auth`, `/api/token` | 5/sec, 100/min, 1,000/hour | 1 MB |
| `/api/orders`, `/orders/*` | 3/sec, 60/min, 5,000/hour | 1 MB |
| `/api/products` | 20/sec, 50,000/hour | 1 MB |
| `/api/orders/webhook` | 10/sec, 10,000/hour | 2 MB |

All limits use Kong's local fixed-window policy.

## Main User Flow

```text
Register through /api/auth/register
  -> FastAPI creates inactive identity user
  -> FastAPI logs simulated email verification URL
  -> FastAPI syncs inactive shadow user into Django
  -> Verify email through /api/auth/verify-email/<token>
  -> FastAPI activates identity user and Django shadow user
  -> Login through /api/auth/login
  -> Receive Kong-verifiable access token and refresh token
  -> Browse public products
  -> Create protected order with Bearer token
  -> Kong verifies JWT
  -> Django maps verified identity to request.user
  -> Django locks product rows and deducts stock
  -> Celery invoice/email task starts after commit
  -> Create Stripe checkout session
  -> Pay on Stripe
  -> Stripe webhook marks order as paid
```

## Important Business Rules

- FastAPI owns real credentials, password security, JWT creation, refresh
  rotation, logout, and account recovery.
- Django owns ecommerce records, shadow users, catalog data, order ownership,
  stock integrity, Stripe checkout, and Stripe webhook handling.
- Kong owns public routing, JWT verification for protected routes, fixed-window
  route limits, and request-size limits.
- Redis stores Celery messages/results and refresh-token blacklist entries.
- Celery runs post-order invoice/email simulation only after the order
  transaction commits.
- Stripe is the source of truth for moving an order from `pending` to `paid`.

Order integrity rules:

- Product stock is checked inside a database transaction.
- Product rows are locked with `select_for_update()` during order creation.
- Insufficient stock raises a validation error and rolls back the transaction.
- Order item prices are copied at purchase time.
- Celery task dispatch happens through `transaction.on_commit()`.
- Celery does not change payment status.

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
validate required environment variables at startup. Stripe key format validation
is available in `config/env_validator.py`.

Security note: `gateway/kong.yml` currently contains a local JWT credential
secret. For production-style deployment, generate this config from a secret
manager or deployment-time input instead of committing real credentials.

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

Regenerate Kong config from `gateway/kong.template.yml` and `.env`:

```bash
make kong-config
```

Regenerate config and restart only Kong:

```bash
make kong-reload
```

## API Walkthrough

The file `api_tests.rest` contains the current manual request flow.

Password validation currently requires at least 12 characters with uppercase,
lowercase, digit, and special character. Example:

```text
StrongerP@ss123
```

Register:

```http
POST http://127.0.0.1:8080/api/auth/register
Content-Type: application/json

{
  "email": "daanish@test.com",
  "password": "StrongerP@ss123"
}
```

Then copy the simulated verification URL from `identity_service` logs and call
it through Kong:

```http
GET http://127.0.0.1:8080/api/auth/verify-email/<token>
```

Login:

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

Refresh:

```http
POST http://127.0.0.1:8080/api/auth/refresh
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}
```

Logout:

```http
POST http://127.0.0.1:8080/api/auth/logout
Content-Type: application/json

{
  "refresh_token": "<refresh_token>"
}
```

Browse products:

```http
GET http://127.0.0.1:8080/api/products/items/
```

Create order:

```http
POST http://127.0.0.1:8080/api/orders/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "items": [
    {
      "product": 1,
      "quantity": 1
    }
  ]
}
```

Create Stripe Checkout session:

```http
POST http://127.0.0.1:8080/api/orders/<order_id>/create-checkout-session/
Authorization: Bearer <access_token>
Content-Type: application/json

{}
```

Stripe webhook:

```http
POST http://127.0.0.1:8080/api/orders/webhook/
Stripe-Signature: <stripe_signature>
```

The webhook is public at Kong but protected inside Django by Stripe signature
verification.

## Testing and Quality

Run Django tests:

```bash
docker-compose exec order-service pytest
```

Run gateway verification helper:

```bash
python gateway_test.py
```

Run common quality tools from the repository root:

```bash
ruff check .
black --check .
isort --check-only .
mypy .
```

Current Django tests focus on:

- User registration.
- Product creation.
- Successful order creation.
- Stock deduction.
- Insufficient stock rejection.

## Project Progress

Completed milestones:

1. Django REST foundation with users, products, orders, serializers, viewsets,
   routers, and tests.
2. Ecommerce business rules for order ownership, stock checks, stock deduction,
   and price snapshots.
3. Redis/Celery background processing after order creation.
4. Stripe Checkout and webhook payment confirmation.
5. Docker Compose runtime for PostgreSQL, Redis, Django, FastAPI, Celery, and
   gateway.
6. Identity split into FastAPI with Django shadow-user sync.
7. Kong gateway migration with public route exceptions and protected order
   routes.
8. Kong-compatible JWT issuer alignment: `iss = ecom_identity_v1`.
9. Split Django settings with development/production modules and production
   environment validation.
10. Refresh-token rotation, logout, Redis blacklist, email verification,
    password reset, lockouts, and progressive failed-login delay.
11. Route-specific Kong rate limiting and request-size limiting.

Current cleanup targets:

- Move Kong JWT secret injection fully to deployment-time config.
- Rotate any real credentials that ever matched local test values.
- Decide whether `/admin/`, `/static/`, and `/api/users/` should be exposed
  through Kong.
- Prefer `/api/orders/<id>/create-checkout-session/` over the legacy `/orders/*`
  route when updating clients.
- Add a refresh-token/session table if multiple devices need independent active
  sessions.
- Normalize the remaining auth error responses and expand tests around identity
  security flows.

## Final Summary

This project now demonstrates an end-to-end backend engineering journey:

```text
Django monolith
  -> tested ecommerce domain model
  -> Redis/Celery async processing
  -> Stripe checkout and webhook lifecycle
  -> Dockerized production-style runtime
  -> FastAPI identity microservice
  -> inter-service shadow-user sync
  -> Kong gateway migration
  -> edge JWT verification
  -> public route exceptions
  -> route-specific gateway rate limiting and request-size limiting
  -> split settings and environment validation
  -> refresh-token rotation, logout, email verification, password reset,
     lockouts, and progressive failed-login delay
```

The result is a layered ecommerce backend with identity separation, gateway
security, transactional order integrity, async side effects, and payment
confirmation.
# BookMyStay
