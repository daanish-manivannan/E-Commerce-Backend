# E-Commerce Backend Project Overview

This document captures the current architecture, implementation progress, and
remaining cleanup for the ecommerce backend.

In one sentence: FastAPI owns identity and sessions, Kong owns the public edge,
Django owns ecommerce business logic, PostgreSQL stores data, Redis backs Celery
and token revocation state, Celery runs background work, and Stripe confirms
payments.

## Progress Status

Current status: core microservice split, gateway security, commerce flow, and
identity hardening are implemented.

Completed:

- Code quality tools: `ruff`, `black`, `isort`, `mypy`, and pre-commit.
- Django settings split into `base`, `development`, and `production`.
- Production environment validation for critical secrets/config.
- Docker Compose runtime for PostgreSQL, Redis, Django, FastAPI, Celery worker,
  Celery beat, and Kong.
- Kong gateway migration from the older Nginx setup.
- Kong route-specific rate limiting and request-size limiting.
- Kong JWT verification for protected order routes.
- Public Kong exceptions for auth, product catalog, Stripe webhook, and token
  compatibility routes.
- FastAPI registration, login, refresh, logout, email verification, forgot
  password, reset password, failed-login counters, email/IP lockouts, and
  progressive failed-login delay.
- FastAPI to Django shadow-user sync through `INTERNAL_CLUSTER_SECRET`.
- Django catalog reads, authenticated order creation, stock locking, price
  snapshots, Stripe checkout, Stripe webhook, and Celery post-order task
  dispatch after transaction commit.

Still open:

- Production-grade secret injection for Kong JWT credentials.
- More identity-service tests around email verification, password reset,
  refresh rotation, logout, and lockouts.
- Decision on whether admin/static/user routes should be exposed through Kong.
- Optional multi-device session model.
- Cleanup of a few legacy compatibility routes and error-response rough edges.

## High-Level Architecture

```text
Client / API Tester / Frontend
      |
      v
Kong API Gateway
Host: http://127.0.0.1:8080
      |
      |-- /api/auth/*            -> FastAPI Identity Service :8001
      |-- /api/products/*        -> Django Order & Catalog Service :8000
      |-- /api/orders/webhook/*  -> Django Stripe webhook :8000
      |-- /api/orders/*          -> Django orders API :8000, JWT protected
      |-- /orders/*              -> Kong rewrite to Django order checkout
      |-- /api/token/*           -> Django SimpleJWT compatibility route
              |
              v
        PostgreSQL Database
              |
              v
        Redis + Celery Worker / Beat
```

Kong is the active gateway in `docker-compose.yml`. The older Nginx gateway
configuration is retained as prior configuration, but it is not the current
runtime path.

## Runtime Services

| Service | Container | Role |
| --- | --- | --- |
| `db` | `ecom_postgres` | PostgreSQL 15 database |
| `redis` | `ecom_redis` | Redis broker/result backend and token blacklist store |
| `identity_service` | `ecom_identity` | FastAPI identity/auth service |
| `order-service` | `ecom_django` | Django catalog, orders, Stripe, admin |
| `order_worker` | `ecom_worker` | Celery worker |
| `order_beat` | `ecom_beat` | Celery beat scheduler |
| `gateway` | `ecom_gateway` | Kong public API gateway |

Startup flow:

```text
1. PostgreSQL and Redis start.
2. Health checks confirm both are ready.
3. Django, Celery worker, Celery beat, and FastAPI start.
4. Kong starts and exposes host port 8080.
5. Client traffic reaches backend services only through Kong by default.
```

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

Current public route map:

| Route | Backend | Auth |
| --- | --- | --- |
| `/api/auth` | FastAPI identity service | Public |
| `/api/products` | Django product/category APIs | Public |
| `/api/orders/webhook` | Django Stripe webhook | Stripe signature in Django |
| `/api/orders` | Django orders API | Kong JWT |
| `/orders/*` | Rewritten to `/api/orders/*` | Kong JWT |
| `/api/token` | Django SimpleJWT compatibility endpoints | Public |

Kong plugins:

```text
jwt
  Protected order and legacy checkout routes verify JWT exp at the edge.

rate-limiting
  Auth/token: 5/sec, 100/min, 1,000/hour.
  Orders/legacy checkout: 3/sec, 60/min, 5,000/hour.
  Products: 20/sec, 50,000/hour.
  Stripe webhook: 10/sec, 10,000/hour.

request-size-limiting
  Auth/token/products/orders/legacy checkout: 1 MB.
  Stripe webhook: 2 MB.
```

Kong JWT detail:

```text
Consumer username: identity-service
JWT credential key: ecom_identity_v1
JWT algorithm: HS256
Verified claim: exp
```

The FastAPI access token includes `iss = ecom_identity_v1`, which allows Kong to
select the matching JWT credential.

## Identity Service

Folder:

```text
Identity Service/
```

Technology:

```text
FastAPI + SQLAlchemy + PostgreSQL + passlib/bcrypt + python-jose + Redis
```

Important files:

```text
main.py
  Routes, Redis blacklist checks, email/IP lockout logic, shadow-user sync.

models.py
  SQLAlchemy identity user table.

schemas.py
  Pydantic request/response schemas and password strength validators.

auth_utils.py
  Password hashing, JWT access-token creation, refresh-token generation.

database.py
  SQLAlchemy engine/session setup.
```

Identity table:

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

Password policy:

```text
Minimum length: 12
Must include: uppercase, lowercase, digit, and special character
```

Access-token behavior:

```text
Algorithm: HS256
Lifetime: 15 minutes
Claims: sub, user_id, exp, iss
Issuer: ecom_identity_v1
```

Refresh-token behavior:

```text
Generated as a secure random hex token.
Stored on the identity user row.
Expires after 7 days.
Rotated on /refresh.
Old refresh token is blacklisted in Redis until original expiry.
Logout blacklists the active refresh token and clears it from the user row.
```

Failed-login protection:

```text
Email lockout: 5 failed attempts -> locked for 15 minutes.
IP lockout: 20 failed attempts -> locked for 15 minutes.
Progressive delay: begins at attempt 3 with a 2 second delay.
Redis stores counters and lockout keys.
```

Redis key patterns:

```text
auth:failed:email:<email>
auth:lockout:email:<email>
auth:failed:ip:<ip>
auth:lockout:ip:<ip>
blacklist:token:<refresh_token>
```

## Identity Flows

### Registration

External endpoint:

```text
POST /api/auth/register
```

Internal FastAPI route:

```text
POST /register
```

Flow:

```text
1. Client sends email and password through Kong.
2. FastAPI validates password strength.
3. FastAPI checks whether email already exists in identity_users.
4. FastAPI hashes the password.
5. FastAPI creates an inactive identity user.
6. FastAPI creates an email verification token.
7. FastAPI logs a simulated verification URL.
8. FastAPI calls Django internal sync endpoint with is_active=false.
9. Django creates or updates the matching inactive shadow user.
```

The registration flow intentionally keeps users inactive until email
verification completes.

### Email Verification

External endpoint:

```text
GET /api/auth/verify-email/<token>
```

Flow:

```text
1. FastAPI finds the identity user by verification token.
2. FastAPI rejects missing or expired tokens.
3. FastAPI marks email_verified=true and is_active=true.
4. FastAPI clears the verification token.
5. FastAPI syncs the Django shadow user with is_active=true.
```

### Login

External endpoint:

```text
POST /api/auth/login
```

Flow:

```text
1. FastAPI checks IP and email lockout state.
2. FastAPI verifies email/password without leaking which part failed.
3. Failed attempts increment Redis counters.
4. Repeated failures may trigger progressive delay or lockout.
5. Unverified email addresses are rejected.
6. Successful login clears failed-attempt state.
7. FastAPI returns an access token and refresh token.
```

### Refresh

External endpoint:

```text
POST /api/auth/refresh
```

Flow:

```text
1. FastAPI checks whether the refresh token is blacklisted in Redis.
2. FastAPI finds the user with the current refresh token.
3. FastAPI rejects missing, expired, invalid, or blacklisted tokens.
4. FastAPI creates a new access token and new refresh token.
5. FastAPI blacklists the old refresh token until its original expiry.
6. FastAPI stores the new refresh token and expiry.
```

### Logout

External endpoint:

```text
POST /api/auth/logout
```

Flow:

```text
1. FastAPI finds the user by refresh token.
2. FastAPI blacklists the refresh token in Redis until remaining expiry.
3. FastAPI clears refresh_token and refresh_token_expiry from the user row.
```

### Password Reset

Endpoints:

```text
POST /api/auth/forgot-password
POST /api/auth/reset-password
```

Flow:

```text
1. Forgot-password always returns a generic success message.
2. Existing users receive a simulated reset URL in logs.
3. Reset-password validates the token and new password strength.
4. FastAPI updates the password hash.
5. Any active refresh token is blacklisted and cleared.
6. Reset token and expiry are cleared.
```

## Order & Catalog Service

Folder:

```text
Order & Catalog Service/
```

Technology:

```text
Django + Django REST Framework + PostgreSQL + Celery + Redis + Stripe + WhiteNoise
```

Important apps:

```text
users/
  Custom email-based Django user and optional local registration endpoint.

products/
  Category and product catalog.

orders/
  Order creation, order items, internal user sync, Stripe checkout, webhook.

config/
  Settings, URLs, Celery config, custom authentication, exception handling.
```

## Django Settings

Settings modules:

```text
config/settings/base.py
config/settings/development.py
config/settings/production.py
```

Base settings define shared installed apps, middleware, DRF config, Celery
config, Stripe config, static settings, and JSON logging.

Development settings:

```text
DEBUG = True
PostgreSQL defaults for local/Docker development.
Build-mode SQLite fallback for collectstatic.
Verbose logging.
Development ALLOWED_HOSTS includes localhost, order-service, and gateway.
```

Production settings:

```text
DEBUG = False
validate_required_env_vars() runs on startup.
PostgreSQL connection persistence is enabled.
SSL redirect, secure cookies, HSTS, and CSP settings are enabled/configurable.
```

Environment validation:

```text
config/env_validator.py
  Validates required production environment variables.
  Can validate Stripe key prefixes when run directly.
```

## Django Authentication Boundary

File:

```text
Order & Catalog Service/config/authentication.py
```

DRF uses:

```text
config.authentication.KongJWTAuthentication
```

Behavior:

```text
1. If Kong-injected X-User-Email exists, Django gets or creates that user.
2. Otherwise Django reads the Bearer token.
3. Django requires X-Consumer-Username=identity-service as proof that Kong
   already verified the token.
4. Django decodes non-sensitive claims without verifying the signature again.
5. Django maps the email claim to request.user.
```

The security boundary is Kong: protected order requests should enter Django only
after Kong JWT verification succeeds.

## Catalog Flow

Files:

```text
products/models.py
products/serializers.py
products/views.py
products/urls.py
```

Models:

```text
Category
  name
  description
  is_active
  created_at

Product
  category
  name
  description
  price
  stock
  is_active
  created_at
  updated_at
```

Routes:

```text
GET /api/products/categories/
GET /api/products/categories/<id>/
GET /api/products/items/
GET /api/products/items/<id>/
```

Catalog behavior:

```text
ReadOnlyModelViewSet
AllowAny permissions
Only active categories/products are returned
No public create/update/delete through these viewsets
Kong exposes /api/products without JWT
```

## Order Flow

Files:

```text
orders/models.py
orders/serializers.py
orders/views.py
orders/urls.py
orders/tasks.py
```

Models:

```text
Order
  user
  status
  created_at
  updated_at

OrderItem
  order
  product
  price
  quantity
```

Order statuses:

```text
pending
paid
shipped
delivered
cancelled
```

Create order endpoint:

```text
POST /api/orders/
```

Payload:

```json
{
  "items": [
    {
      "product": 1,
      "quantity": 2
    }
  ]
}
```

Create order flow:

```text
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

Order list/retrieve behavior:

```text
OrderViewSet.get_queryset() filters by request.user.
Users can only see their own orders.
```

## Payment Flow

Provider:

```text
Stripe
```

Create checkout endpoint:

```text
POST /api/orders/<order_id>/create-checkout-session/
```

Legacy compatibility endpoint:

```text
POST /orders/<order_id>/create-checkout-session/
```

Checkout flow:

```text
1. Kong validates JWT.
2. Django resolves the order through the current user's queryset.
3. Django rejects checkout unless order.status is pending.
4. Django converts OrderItems to Stripe line items.
5. Django creates a Stripe Checkout Session.
6. Stripe receives client_reference_id = order.id.
7. Django returns checkout_url.
```

Stripe webhook endpoint:

```text
POST /api/orders/webhook/
```

Webhook flow:

```text
1. Stripe calls the public webhook route through Kong.
2. Kong does not require JWT on this route.
3. Django reads the raw body and Stripe-Signature header.
4. Django verifies the signature with STRIPE_WEBHOOK_SECRET.
5. checkout.session.completed marks pending orders as paid.
6. payment_intent.payment_failed is logged.
7. Django returns HTTP 200 for handled events.
```

## Background Task Flow

Files:

```text
orders/tasks.py
config/celery.py
```

Celery settings:

```text
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
CELERY_ACCEPT_CONTENT=["json"]
CELERY_TASK_SERIALIZER=json
CELERY_RESULT_SERIALIZER=json
CELERY_TIMEZONE=UTC
```

Current task:

```text
orders.tasks.fulfill_and_send_invoice_task(order_id)
```

Behavior:

```text
1. Order creation commits successfully.
2. transaction.on_commit() queues the Celery task.
3. Redis stores the task message.
4. Celery worker fetches the order.
5. Worker simulates invoice generation and email dispatch.
6. Worker leaves payment status unchanged.
```

This keeps payment lifecycle ownership clean: Celery handles side effects,
Stripe webhook handles `pending -> paid`.

## Database Design

Main tables:

```text
identity_users
users_customuser
products_category
products_product
orders_order
orders_orderitem
```

Relationships:

```text
Identity User
  Real auth/password/session record owned by FastAPI.

Django CustomUser
  Shadow/local user used by Django request.user and order ownership.

Category
  Has many Products.

Product
  Belongs to Category.
  Has many OrderItems.
  Stores current stock and price.

Order
  Belongs to a Django CustomUser.
  Has many OrderItems.
  Tracks lifecycle status.

OrderItem
  Belongs to an Order.
  Belongs to a Product.
  Stores price snapshot and quantity.
```

## Environment Variables

Important variables:

```text
DEBUG
SECRET_KEY
JWT_SECRET
INTERNAL_CLUSTER_SECRET
REDIS_URL
STRIPE_PUBLIC_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT
DATABASE_URL
ALLOWED_HOSTS
```

Variable responsibilities:

```text
SECRET_KEY
  Django internal cryptographic secret.

JWT_SECRET
  HS256 signing secret used by FastAPI and matched by Kong JWT credentials.

INTERNAL_CLUSTER_SECRET
  Private service-to-service secret for FastAPI -> Django shadow-user sync.

REDIS_URL
  FastAPI Redis connection for refresh-token blacklist and auth lockout state.

STRIPE_* values
  Django Stripe Checkout and webhook verification config.

POSTGRES_* / DATABASE_URL
  Database settings for Django and FastAPI containers.
```

## Testing and Tooling

Testing:

```text
pytest
pytest-django
Django REST Framework APIClient
api_tests.rest
gateway_test.py
```

Current Django tests cover:

```text
User registration
Product creation
Successful order creation
Stock deduction
Insufficient stock rejection
```

Quality tools:

```text
ruff
black
isort
mypy
pre-commit
```

## Phase History

### Phase 1: Django Foundation

Built the original Django REST API with custom email users, product/category
models, order/order item models, serializers, viewsets, routers, and tests.

### Phase 2: Auth and Core API

Added authenticated user workflows, initial JWT behavior, user registration, and
user-scoped order history.

### Phase 3: Catalog, Orders, and Business Rules

Implemented public catalog reads, nested order creation, stock checks, stock
deduction, insufficient-stock rejection, and price snapshots.

### Phase 4: Async Processing

Added Redis and Celery. Moved post-order invoice/email simulation out of the API
request cycle and later adjusted dispatch to use `transaction.on_commit()`.

### Phase 5: Stripe Payments

Added Stripe Checkout Session creation, order ownership checks, pending-only
checkout validation, webhook signature verification, and `pending -> paid`
updates from `checkout.session.completed`.

### Phase 6: Docker Runtime

Added Dockerfiles and `docker-compose.yml` for PostgreSQL, Redis, Django, FastAPI,
Celery worker, Celery beat, and gateway services.

### Phase 7: Microservice Split

Separated identity into FastAPI while keeping Django responsible for commerce.
Introduced the shadow-user pattern so Django can still associate orders with a
local user.

### Phase 8: Internal Sync

Connected FastAPI registration and email verification to Django's internal
`/api/orders/users/sync/` endpoint using `INTERNAL_CLUSTER_SECRET`.

### Phase 9: Kong Gateway Migration

Moved from the old Nginx gateway to Kong DB-less config. Added public auth,
product, webhook, token, protected order, and legacy checkout routes.

### Phase 10: JWT Boundary Alignment

Aligned FastAPI issuer, Kong JWT credentials, and Django request authentication.
FastAPI emits `iss=ecom_identity_v1`, Kong verifies tokens, and Django maps the
verified identity to `request.user`.

### Phase 11: Gateway Security

Added route-specific rate limits and request-size limits across auth, token,
products, orders, legacy checkout, and Stripe webhook routes.

### Phase 12: Settings and Env Cleanup

Split Django settings into base/development/production modules, removed duplicate
database configuration, added production env validation, and made Celery result
serialization/timezone explicit.

### Phase 13: Identity Security Hardening

Added short-lived access tokens, refresh-token rotation, logout, Redis
blacklisting, email verification, password reset, password strength validation,
failed-login counters, IP/email lockouts, and progressive delay.

## Current Strengths

- Clear separation between identity and ecommerce responsibilities.
- Kong centralizes public routing, JWT verification, rate limiting, and payload
  protection.
- Public catalog and Stripe webhook routes are explicit exceptions.
- Application service ports are internal-only behind Kong in the main runtime.
- Internal user sync uses a dedicated secret instead of public JWT material.
- Access tokens are short-lived and refresh tokens can be rotated or revoked.
- Failed-login abuse protection exists in the identity service.
- Order creation uses transactions and product row locks.
- Order item prices are historical snapshots.
- Celery work starts only after database commit.
- Stripe signature verification guards payment status changes.
- Django settings are split by environment and production validates required
  config.

## Current Cleanup Items

| Area | Current note | Suggested direction |
| --- | --- | --- |
| Kong JWT secret | `gateway/kong.yml` contains a local JWT credential secret. | Generate Kong config from deployment-managed secrets and avoid committing real credentials. |
| Secret history | Prior development values may exist in Git history. | Rotate any matching real credentials before production and run secret scanning. |
| Header mapping | Django can use `X-User-Email` headers, but protected order routes currently rely on the Kong verification marker plus token claims. | Add an explicit Kong request-transformer or simplify Django auth around the verified-token fallback. |
| Admin/static exposure | Django supports `/admin/` and `/static/`, but Kong does not expose them. | Keep internal-only intentionally or add explicit locked-down Kong routes. |
| Legacy checkout route | `/orders/*` exists for API spec compatibility. | Prefer `/api/orders/<id>/create-checkout-session/` in new clients. |
| Multi-device sessions | Identity stores one active refresh token per user. | Add a separate session/refresh-token table if independent device sessions are required. |
| Identity test coverage | Commerce tests exist, but identity security flows need broader automated coverage. | Add tests for verification, reset, refresh rotation, logout, lockout, and generic error behavior. |
| Error response consistency | Most identity errors use a standard body, but a few paths still need normalization. | Consolidate all identity errors through the same helper and add regression tests. |

## Current Request Maps

Registration:

```text
Client
  -> Kong /api/auth/register
  -> FastAPI /register
  -> PostgreSQL identity_users
  -> Django /api/orders/users/sync/
  -> PostgreSQL users_customuser
```

Email verification:

```text
Client
  -> Kong /api/auth/verify-email/<token>
  -> FastAPI activates identity user
  -> Django /api/orders/users/sync/
  -> Django activates shadow user
```

Login:

```text
Client
  -> Kong /api/auth/login
  -> FastAPI /login
  -> Redis lockout checks
  -> FastAPI verifies password
  -> FastAPI returns access + refresh tokens
```

Create order:

```text
Client + Bearer token
  -> Kong /api/orders/
  -> Kong JWT plugin
  -> Django KongJWTAuthentication
  -> OrderSerializer transaction
  -> Product row locks and stock deduction
  -> OrderItem price snapshots
  -> Celery task after commit
```

Checkout and webhook:

```text
Client + Bearer token
  -> Kong /api/orders/<id>/create-checkout-session/
  -> Django creates Stripe Checkout Session
  -> Stripe hosted payment page
  -> Stripe /api/orders/webhook/
  -> Django verifies Stripe signature
  -> Order marked paid
```

## Clean Target Architecture

```text
Kong owns:
  Public routing.
  JWT verification for protected APIs.
  Public exceptions for auth, catalog, token, and Stripe webhook routes.
  Route-specific rate limiting.
  Request-size limiting.

FastAPI owns:
  Identity users.
  Password hashing and password policy.
  Email verification.
  Password reset.
  JWT access-token creation.
  Refresh-token rotation and logout.
  Failed-login counters, lockouts, and progressive delay.
  Shadow-user sync requests.

Django owns:
  Shadow users for request ownership.
  Catalog data.
  Order creation and stock integrity.
  Stripe checkout and webhook logic.
  Admin and business records.

Redis owns:
  Celery broker/result state.
  Refresh-token blacklist entries.
  Failed-login and lockout counters.

Celery owns:
  Background invoice/email simulation after order commit.

PostgreSQL owns:
  Identity users.
  Django shadow users.
  Catalog, orders, and order items.
```
