# E-Commerce Backend Platform

A containerized ecommerce backend built as a small microservice-style system.

The project started as a Django REST API and evolved phase by phase into a distributed backend with:

- FastAPI for identity, registration, login, password hashing, and JWT creation.
- Django REST Framework for catalog, orders, stock control, Stripe checkout, webhooks, admin, and business logic.
- Kong API Gateway for public routing, JWT verification at the edge, public route exceptions, and fixed-window rate limiting.
- PostgreSQL for identity, users, products, orders, and order items.
- Redis and Celery for background invoice/email simulation.
- Stripe Checkout and Stripe webhooks for payment flow.

---

## Current Architecture

```text
Client / API Tester / Frontend
      |
      v
Kong API Gateway
Host: 127.0.0.1:8080
      |
      |-- /api/auth/*            -> FastAPI Identity Service :8001
      |
      |-- /api/products/*        -> Django Order & Catalog Service :8000
      |
      |-- /api/orders/webhook/*  -> Django Stripe Webhook :8000
      |
      |-- /api/orders/*          -> Django Orders API :8000, JWT protected
      |
      |-- /orders/*              -> Legacy checkout compatibility route
              |
              v
        PostgreSQL + Redis
              |
              v
        Celery Worker / Beat
```

Kong replaced the earlier Nginx gateway so authentication, routing exceptions, and rate limiting can be handled at the gateway layer.

---

## Tech Stack

| Layer | Technology |
| --- | --- |
| API Gateway | Kong 3.4, DB-less declarative config |
| Identity Service | FastAPI, SQLAlchemy, bcrypt, python-jose, python-decouple |
| Commerce Service | Django, Django REST Framework, WhiteNoise |
| Database | PostgreSQL 15 |
| Background Jobs | Redis 7, Celery |
| Payments | Stripe Checkout, Stripe Webhooks |
| Auth | HS256 JWT, Kong JWT plugin, custom Django gateway authentication |
| Testing | pytest, pytest-django, DRF APIClient, REST Client scratch file |
| Infrastructure | Docker, Docker Compose |

---

## Service Map

```text
db
  PostgreSQL database for both services.

redis
  Broker and result backend for Celery.

identity_service
  FastAPI service. Owns identity_users, password hashes, JWT creation, and shadow-user sync.

order-service
  Django service. Owns catalog, orders, Stripe checkout/webhook, admin, and ecommerce business rules.

order_worker
  Celery worker. Runs post-order background invoice/email simulation.

order_beat
  Celery beat scheduler.

gateway
  Kong gateway exposed on host port 8080.
```

---

## Phase-Wise Implementation Journey

### Phase 1: Django Foundation

Built the initial Django backend structure with modular apps for users, products, and orders.

Implemented:

- Django project/app structure.
- Custom email-based `CustomUser`.
- Product and category models.
- Order and order item models.
- DRF serializers, viewsets, routers, and basic API behavior.

### Phase 2: Auth and Core API

Added authentication and protected ecommerce workflows.

Implemented:

- JWT-based access through Django/SimpleJWT during the early monolith phase.
- User registration flow.
- Authenticated order creation.
- User-scoped order history.

### Phase 3: Catalog, Orders, and Business Rules

Implemented the main ecommerce domain logic.

Implemented:

- Public product/category reads.
- Order creation with nested order items.
- Product price snapshot into `OrderItem.price`.
- Stock validation.
- Insufficient-stock rejection.
- Tests for product creation, order creation, stock deduction, and stock failure paths.

### Phase 4: Async Processing

Moved slow post-order work out of the API request cycle.

Implemented:

- Redis broker.
- Celery worker.
- `fulfill_and_send_invoice_task(order_id)`.
- Background invoice/email simulation.
- Task dispatch after successful order creation.

Later fix:

- Removed duplicate task dispatch.
- Moved task scheduling to `transaction.on_commit()` so Celery runs only after the order transaction safely commits.
- Stopped the worker from changing order status to an invalid `completed` value.

### Phase 5: Stripe Payments

Added payment flow and payment confirmation.

Implemented:

- Stripe Checkout Session creation.
- Order ownership checks before checkout.
- Checkout allowed only for `pending` orders.
- `client_reference_id = order.id` to connect Stripe sessions back to local orders.
- Stripe webhook signature verification.
- `checkout.session.completed` handling.
- Order state transition from `pending` to `paid`.

### Phase 6: Docker and Production Hardening

Prepared the system for repeatable local and containerized runs.

Implemented:

- Dockerfiles for Django and FastAPI services.
- `docker-compose.yml` for PostgreSQL, Redis, Django, Celery worker, Celery beat, FastAPI, and gateway.
- Health checks for PostgreSQL and Redis.
- WhiteNoise static-file support.
- Structured logging.
- Shared static volume for Django assets.
- Internal-only application service ports via `expose`.

### Phase 7: Microservice Split

Split identity from commerce.

Implemented:

- FastAPI Identity Service.
- Django Order & Catalog Service.
- Shared PostgreSQL database with separate identity and Django user tables.
- Shadow-user pattern so FastAPI owns real credentials while Django still has a local user row for order ownership.

### Phase 8: Inter-Service Sync

Connected registration in FastAPI to Django user provisioning.

Implemented:

- FastAPI calls Django internal sync endpoint:

```text
http://order-service:8000/api/orders/users/sync/
```

- Django verifies `X-Internal-Secret`.
- Secret source moved to `INTERNAL_CLUSTER_SECRET`.
- Django uses `get_or_create` inside `transaction.atomic()` to keep sync idempotent.

### Phase 9: Gateway Migration

Moved from Nginx to Kong.

Implemented:

- Kong DB-less declarative config in `gateway/kong.yml`.
- Public auth route to FastAPI.
- Public product catalog route to Django.
- Public Stripe webhook route to Django.
- Protected orders route with Kong JWT plugin.
- Legacy checkout route rewrite for API spec compatibility.

### Phase 10: Cross-Service JWT Alignment

Aligned FastAPI token creation, Kong JWT verification, and Django request authentication.

Implemented:

- FastAPI emits `iss = ecom_identity_v1`.
- Kong JWT credential key matches `ecom_identity_v1`.
- Kong validates JWT expiration.
- Django uses `KongJWTAuthentication`.
- Django maps Kong-verified identity to `request.user`.
- Django can use Kong headers when present or read non-sensitive claims after Kong verification.

### Phase 11: Gateway Route Fixes

Resolved mismatches between Django permissions and gateway behavior.

Implemented:

- `/api/products` is public at Kong, matching Django `AllowAny` read behavior.
- `/api/orders/webhook` is public at Kong, while Django still verifies Stripe signatures.
- `/api/orders` remains JWT protected.
- `api_tests.rest` now targets Kong on `http://127.0.0.1:8080`.

### Phase 12: Gateway Rate Limiting

Added global gateway protection.

Implemented:

```text
5 requests per second per IP
10,000 requests per hour per IP
policy: local
```

This is configured as a global Kong `rate-limiting` plugin.

### Phase 13: Celery Result and Time Handling

Made Celery result behavior more explicit.

Implemented:

```text
CELERY_RESULT_SERIALIZER = json
CELERY_TIMEZONE = UTC
```

This keeps worker result state tracking predictable and aligns background task timing with the rest of the backend.

---

## Current Public Gateway Routes

Base URL:

```text
http://127.0.0.1:8080
```

| Route | Service | Auth | Purpose |
| --- | --- | --- | --- |
| `POST /api/auth/register` | FastAPI | Public | Register identity user and sync Django shadow user |
| `POST /api/auth/login` | FastAPI | Public | Login and receive JWT |
| `GET /api/products/categories/` | Django | Public | List categories |
| `GET /api/products/items/` | Django | Public | List products |
| `POST /api/orders/` | Django | JWT | Create order |
| `GET /api/orders/` | Django | JWT | List current user's orders |
| `POST /api/orders/<id>/create-checkout-session/` | Django | JWT | Create Stripe Checkout session |
| `POST /api/orders/webhook/` | Django | Stripe signature | Receive Stripe payment events |
| `POST /orders/<id>/create-checkout-session/` | Kong rewrite -> Django | JWT | Legacy checkout route compatibility |

---

## Main User Flow

```text
Register through /api/auth/register
  -> FastAPI creates identity user
  -> FastAPI syncs shadow user into Django
  -> Login through /api/auth/login
  -> Receive Kong-verifiable JWT
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

---

## Important Business Rules

```text
FastAPI owns real credentials and JWT creation.
Django owns ecommerce records and order ownership.
Kong owns public routing, JWT verification, and rate limiting.
Stripe owns payment confirmation.
Celery owns post-order background side effects.
```

Order integrity rules:

- Product stock is checked inside a database transaction.
- Product rows are locked with `select_for_update()` during order creation.
- Order item prices are copied at purchase time.
- Celery task dispatch happens only after transaction commit.
- Celery does not change payment status.
- Stripe webhook changes order status from `pending` to `paid`.

---

## Environment Variables

Create a `.env` file in the project root.

```env
DEBUG=True
SECRET_KEY=your_django_secret
JWT_SECRET=your_shared_hs256_secret
INTERNAL_CLUSTER_SECRET=your_internal_service_secret

POSTGRES_DB=ecom_db
POSTGRES_USER=ecom_user
POSTGRES_PASSWORD=ecom_password
POSTGRES_HOST=db
POSTGRES_PORT=5432

DATABASE_URL=postgresql://ecom_user:ecom_password@db:5432/ecom_db

STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

Security note:

```text
gateway/kong.yml currently contains a local JWT credential secret.
For a production-style deployment, inject this at deploy time instead of committing a real secret.
```

---

## Run Locally

Start the full stack:

```bash
docker-compose up --build
```

Or run in detached mode:

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

---

## API Walkthrough

The file `api_tests.rest` contains the current manual request flow.

### 1. Register

```http
POST http://127.0.0.1:8080/api/auth/register
Content-Type: application/json

{
  "email": "daanish@test.com",
  "password": "P@ssword"
}
```

### 2. Login

```http
POST http://127.0.0.1:8080/api/auth/login
Content-Type: application/json

{
  "email": "daanish@test.com",
  "password": "P@ssword"
}
```

Response includes:

```json
{
  "access_token": "...",
  "token_type": "bearer"
}
```

### 3. Browse Products

```http
GET http://127.0.0.1:8080/api/products/items/
```

### 4. Create Order

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

### 5. Create Stripe Checkout Session

```http
POST http://127.0.0.1:8080/api/orders/<order_id>/create-checkout-session/
Authorization: Bearer <access_token>
Content-Type: application/json

{}
```

### 6. Stripe Webhook

```http
POST http://127.0.0.1:8080/api/orders/webhook/
Stripe-Signature: <stripe_signature>
```

The webhook is public at Kong but protected inside Django by Stripe signature verification.

---

## Testing

Run Django tests:

```bash
docker-compose exec order-service pytest
```

Current test coverage focuses on:

- user registration
- product creation
- successful order creation
- stock deduction
- insufficient stock rejection

Manual API testing:

```text
api_tests.rest
```

Gateway verification:

```bash
python gateway_test.py
```

---

## Current Strengths

- Clear separation between identity and ecommerce logic.
- Kong centralizes public routing, JWT verification, and rate limiting.
- Application services are internal-only behind the gateway.
- Internal sync uses a dedicated cluster secret instead of public JWT material.
- Order creation uses transactions and product row locks.
- Price snapshots preserve historical order totals.
- Celery work starts after database commit.
- Stripe webhook verification protects payment status changes.
- Public catalog and public webhook routes are explicit gateway exceptions.
- Manual API flow is documented in `api_tests.rest`.

---

## Known Cleanup Items

These are intentionally documented so future work is obvious:

- `config/settings.py` still defines `DATABASES` twice; the hardcoded PostgreSQL block currently wins.
- `gateway/kong.yml` contains a local JWT secret; use deployment-time injection for production.
- `/admin/` and `/static/` are not currently exposed through Kong.
- `/api/users/` is still present in Django but not exposed through Kong.
- `/orders/*` exists for legacy checkout compatibility; prefer `/api/orders/<id>/create-checkout-session/`.
- Header injection from Kong to Django can be simplified or made explicit with a request-transformer on protected order routes.

---

## Repository Guide

```text
Identity Service/
  FastAPI identity microservice.

Order & Catalog Service/
  Django ecommerce service.

gateway/
  Kong and older Nginx gateway configuration.

docker-compose.yml
  Full local stack orchestration.

api_tests.rest
  Manual API flow through Kong.

gateway_test.py
  Gateway behavior verification helper.

PROJECT_OVERVIEW.md
  Detailed architecture and implementation notes.

API Spec Ecom 2.yaml
  API specification artifact.
```

---

## Final Summary

This project demonstrates an end-to-end backend engineering journey:

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
  -> gateway rate limiting
```

The result is more than a CRUD API: it is a layered ecommerce backend with identity separation, gateway security, transactional order integrity, async processing, and payment confirmation.
