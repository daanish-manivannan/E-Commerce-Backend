# E-Commerce Backend Project Overview

This project is a containerized ecommerce backend built with a small microservice-style architecture.

In simple terms:

**FastAPI owns identity and JWT creation. Kong is now the public API gateway and verifies JWTs at the edge. Django handles catalog, orders, payments, admin, and ecommerce business logic. PostgreSQL stores data. Redis and Celery handle background jobs. Stripe handles checkout.**

---

# 1. High-Level Architecture

```text
Client / API Tester / Frontend
      |
      v
Kong API Gateway
Host: 127.0.0.1:8080
      |
      |-- /api/auth/*      -> FastAPI Identity Service :8001
      |
      |-- /api/products/*  -> Django Order & Catalog Service :8000
      |
      |-- /api/orders/*    -> Django Order & Catalog Service :8000
              |
              v
        PostgreSQL Database
              |
              v
        Redis + Celery Worker / Beat
```

Kong has replaced the active Nginx gateway in `docker-compose.yml`. The old Nginx configuration is still present/commented as previous configuration, but the running gateway service is Kong.

---

# 2. Main Services

## Kong API Gateway

Files:

```text
docker-compose.yml
gateway/kong.yml
```

Kong is running in DB-less/declarative mode.

Current gateway behavior:

```text
External port:
  8080

Internal Kong proxy port:
  8000

Admin API:
  disabled
```

Current Kong routes:

```text
/api/auth
  -> FastAPI identity_service:8001

/api/products
  -> Django order-service:8000, public catalog route

/api/orders/webhook
  -> Django order-service:8000, public Stripe webhook route

/api/orders
  -> Django order-service:8000, JWT-protected order route

/orders/*
  -> Django order-service:8000, JWT-protected legacy checkout compatibility route

/api/token
  -> Django order-service:8000, SimpleJWT compatibility route
```

Kong plugins on protected order-service routes:

```text
jwt
  -> Verifies JWT signature and expiration before request reaches Django.
```

The gateway is now responsible for edge-level authentication on the configured order-service routes.

---

## Identity Service

Folder:

```text
Identity Service/
```

Technology:

```text
FastAPI + SQLAlchemy + PostgreSQL + bcrypt + JWT + python-decouple
```

Purpose:

```text
Handles user registration, password hashing, login, JWT creation, and shadow-user sync with Django.
```

Important files:

```text
main.py        -> FastAPI routes
models.py      -> SQLAlchemy identity user model
schemas.py     -> Pydantic request/response schemas
auth_utils.py  -> bcrypt password hashing and Kong-compatible JWT creation
database.py    -> SQLAlchemy database connection/session
Dockerfile     -> FastAPI container setup
```

The identity service stores real login credentials in the `identity_users` table.

---

## Order & Catalog Service

Folder:

```text
Order & Catalog Service/
```

Technology:

```text
Django + Django REST Framework + PostgreSQL + Celery + Redis + Stripe + WhiteNoise
```

Purpose:

```text
Handles catalog APIs, Django users, order creation, stock control, Stripe checkout, Stripe webhooks, Django admin, static files, and async order processing.
```

Important apps:

```text
users/     -> Django custom user and optional Django registration endpoint
products/  -> Category and product catalog
orders/    -> Order creation, order items, Stripe checkout, webhook, internal user sync
config/    -> Django settings, URLs, Kong header authentication, Celery config
```

---

# 3. Infrastructure

Defined in:

```text
docker-compose.yml
```

Services:

```text
db                -> PostgreSQL database
redis             -> Redis message broker/result backend
order-service     -> Django API container
order_worker      -> Celery worker for background tasks
order_beat        -> Celery beat scheduler
identity_service  -> FastAPI identity/auth service
gateway           -> Kong API Gateway
```

Volumes:

```text
postgres_data  -> Persists PostgreSQL data
django_static  -> Shared Django static files volume
```

Current deployment behavior:

```text
1. PostgreSQL and Redis start first.
2. Health checks confirm they are ready.
3. Django, Celery worker, Celery beat, and FastAPI start after dependencies are healthy.
4. Kong starts and routes external traffic from host port 8080 to internal services.
```

---

# 4. Environment and Secrets

Important environment variables:

```text
DEBUG
SECRET_KEY
JWT_SECRET
INTERNAL_CLUSTER_SECRET
STRIPE_PUBLIC_KEY
STRIPE_SECRET_KEY
STRIPE_WEBHOOK_SECRET
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_HOST
POSTGRES_PORT
DATABASE_URL
```

Purpose:

```text
SECRET_KEY
  -> Django internal cryptographic secret.

JWT_SECRET
  -> Shared token signing/verification material used by FastAPI and Kong.

INTERNAL_CLUSTER_SECRET
  -> Private service-to-service passcode for FastAPI -> Django shadow-user sync.

STRIPE_* values
  -> Used by Django for Stripe checkout and webhook verification.
```

Current JWT detail:

```text
Identity Service/auth_utils.py expects JWT_SECRET to be a hex string.
It converts that hex string into bytes using bytes.fromhex().
FastAPI signs JWTs with HS256.
The token includes iss = ecom_identity_v1 so Kong can locate the matching JWT credential.
```

Kong detail:

```text
Kong is configured with a consumer named identity-service.
The JWT credential key is ecom_identity_v1.
Kong validates the JWT exp claim.
```

---

# 5. Authentication Flow

## FastAPI Registration Flow

External endpoint through Kong:

```text
POST /api/auth/register
```

Internal FastAPI route:

```text
POST /register
```

Flow:

```text
1. User sends email and password to FastAPI through Kong.
2. FastAPI checks whether that email already exists in identity_users.
3. FastAPI hashes the password using bcrypt.
4. FastAPI saves the user in PostgreSQL through SQLAlchemy.
5. FastAPI loads INTERNAL_CLUSTER_SECRET using python-decouple.
6. FastAPI calls Django internally at:

   http://order-service:8000/api/orders/users/sync/

7. FastAPI sends the email and X-Internal-Secret header.
8. Django verifies INTERNAL_CLUSTER_SECRET.
9. Django creates or reuses a matching shadow user.
10. Registration completes.
```

Why shadow users exist:

```text
FastAPI owns real authentication and passwords.
Django still needs a local user record so orders can be linked to request.user.
The Django shadow user has the same email but does not need a usable password.
```

---

## FastAPI Login Flow

External endpoint through Kong:

```text
POST /api/auth/login
```

Internal FastAPI route:

```text
POST /login
```

Flow:

```text
1. User sends email and password.
2. FastAPI finds the user in identity_users.
3. FastAPI verifies the bcrypt password hash.
4. FastAPI creates a JWT with:

   sub     -> user email
   user_id -> identity service user ID
   exp     -> expiration time
   iss     -> ecom_identity_v1

5. FastAPI signs the token with HS256.
6. Client sends that token to protected gateway routes using:

   Authorization: Bearer <token>
```

---

## Kong Edge JWT Validation

File:

```text
gateway/kong.yml
```

Flow:

```text
1. Client calls a protected route under /api/products or /api/orders.
2. Kong reads the Authorization header.
3. Kong validates the JWT signature.
4. Kong checks the exp claim.
5. Kong uses the iss claim as the key lookup value.
6. If the token is valid, Kong forwards the request to Django.
7. Django maps the Kong-verified token identity to request.user.
```

---

## Django Gateway Header Authentication

File:

```text
Order & Catalog Service/config/authentication.py
```

Current DRF authentication class:

```text
config.authentication.KongJWTAuthentication
```

Flow:

```text
1. Django receives a request from Kong.
2. Django reads:

   HTTP_X_USER_EMAIL
   HTTP_X_USER_ID

3. If X-User-Email is present, Django gets or creates a CustomUser.
4. If X-User-Email is missing, Django checks that Kong authenticated the request through X-Consumer-Username.
5. If Kong verification is present, Django reads non-sensitive identity claims from the Bearer token.
6. Django binds that user to request.user.
7. DRF permission checks continue normally.
```

Important shift:

```text
Django no longer owns JWT signature verification for protected gateway routes.
Kong verifies the JWT first; Django then maps the verified identity to request.user.
```

---

# 6. Django User Flow

Files:

```text
users/models.py
users/serializers.py
users/views.py
users/urls.py
users/admin.py
```

Main model:

```text
CustomUser
  - email
  - first_name
  - last_name
  - is_active
  - is_staff
  - date_joined
```

Important detail:

```text
AUTH_USER_MODEL = users.CustomUser
```

Django uses email as the login identity instead of username.

There is still a Django registration endpoint:

```text
POST /api/users/register/
```

But this route is not currently exposed by Kong, because Kong routes only `/api/auth`, `/api/products`, and `/api/orders`.

---

# 7. Product / Catalog Flow

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
  - name
  - description
  - is_active
  - created_at

Product
  - category
  - name
  - description
  - price
  - stock
  - is_active
  - created_at
  - updated_at
```

Django route prefix:

```text
/api/products/
```

Main Django routes:

```text
GET /api/products/categories/
GET /api/products/items/
GET /api/products/categories/<id>/
GET /api/products/items/<id>/
```

Django catalog behavior:

```text
1. Categories and products use ReadOnlyModelViewSet.
2. The Django view permissions are AllowAny.
3. Clients cannot create, update, or delete catalog records through these viewsets.
```

Gateway behavior:

```text
Kong now exposes /api/products through a public route without the JWT plugin.
This matches Django's AllowAny catalog read behavior.
```

---

# 8. Order Flow

Files:

```text
orders/models.py
orders/serializers.py
orders/views.py
orders/urls.py
```

Models:

```text
Order
  - user
  - status
  - created_at
  - updated_at

OrderItem
  - order
  - product
  - price
  - quantity
```

Declared order statuses:

```text
pending
paid
shipped
delivered
cancelled
```

Order creation endpoint:

```text
POST /api/orders/
```

Example payload:

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

Current order creation flow:

```text
1. Client sends products and quantities with a Bearer token.
2. Kong validates the JWT.
3. Django maps the Kong-verified identity to request.user.
4. The order is linked to request.user.
5. OrderSerializer starts a database transaction.
6. Django creates the parent Order linked to request.user.
7. For each item, Django re-queries the Product using select_for_update().
8. The product row is locked at database level.
9. Django checks whether stock is available.
10. If stock is insufficient, the transaction rolls back.
11. If stock is available, stock is deducted.
12. Django creates OrderItem rows.
13. Product price is copied into OrderItem.price.
14. After the transaction commits, Django queues a Celery task using transaction.on_commit().
15. API returns the created order.
```

Important business rules:

```text
Stock is protected by a database transaction.
Product rows are locked during order creation to reduce race conditions.
Price is locked at purchase time.
The Celery task is queued only after the database transaction safely commits.
```

---

# 9. Payment Flow

Payment provider:

```text
Stripe
```

Main file:

```text
orders/views.py
```

## Create Stripe Checkout Session

Endpoint:

```text
POST /api/orders/<order_id>/create-checkout-session/
```

Flow:

```text
1. Client sends a valid JWT to Kong.
2. Kong validates the JWT and forwards user headers to Django.
3. Django maps the headers to request.user.
4. Django verifies the order belongs to the current user through get_queryset().
5. Django rejects checkout if the order status is not pending.
6. Django converts each OrderItem into a Stripe line item.
7. Django creates a Stripe Checkout Session.
8. Stripe returns a checkout_url.
9. Client redirects the user to Stripe.
```

Stripe uses:

```text
client_reference_id = order.id
```

That lets the webhook connect the Stripe payment back to the local order.

---

## Stripe Webhook Flow

Endpoint:

```text
POST /api/orders/webhook/
```

Flow:

```text
1. Stripe sends a webhook request to Django.
2. Django reads the raw request body and Stripe-Signature header.
3. Django verifies the webhook using STRIPE_WEBHOOK_SECRET.
4. For checkout.session.completed:
   - Django reads client_reference_id.
   - Django finds the matching Order.
   - If the order is pending, Django marks it paid.
5. For payment_intent.payment_failed:
   - Django logs the failure.
6. Django returns HTTP 200 for handled webhook events.
```

Important routing note:

```text
The webhook path is under /api/orders/webhook/.
Kong now exposes /api/orders/webhook through a public route without the JWT plugin.
Django still protects the endpoint by verifying Stripe's webhook signature.
```

---

# 10. Background Task Flow

Files:

```text
orders/tasks.py
config/celery.py
```

Technology:

```text
Celery + Redis
```

Runtime settings:

```text
CELERY_BROKER_URL       -> redis://redis:6379/0
CELERY_RESULT_BACKEND   -> redis://redis:6379/0
CELERY_ACCEPT_CONTENT   -> json
CELERY_TASK_SERIALIZER  -> json
CELERY_RESULT_SERIALIZER -> json
CELERY_TIMEZONE         -> UTC
```

Current task:

```text
fulfill_and_send_invoice_task(order_id)
```

Task name:

```text
orders.tasks.fulfill_and_send_invoice_task
```

Triggered after:

```text
Successful order creation transaction commit
```

Flow:

```text
1. Django creates an order inside a transaction.
2. After commit, Django queues fulfill_and_send_invoice_task(order.id).
3. Redis stores the task message.
4. Celery worker receives the task.
5. Worker fetches the order by ID.
6. Worker simulates invoice generation and email dispatch.
7. Worker prints/logs task results.
```

Current implementation detail:

```text
The task no longer changes order status.
It simulates invoice/email work and leaves payment state for the Stripe webhook.
```

This keeps the payment lifecycle clean: the worker performs side effects, while Stripe owns `pending -> paid`.

---

# 11. Database Design

Database:

```text
PostgreSQL
```

Main tables:

```text
identity_users
users_customuser
products_category
products_product
orders_order
orders_orderitem
```

Relationship overview:

```text
Identity User
  -> Real login/password record owned by FastAPI.

Django CustomUser
  -> Local Django user/shadow user used for request.user and order ownership.

Category
  -> Has many Products.

Product
  -> Belongs to Category.
  -> Has many OrderItems.
  -> Contains current stock and current price.

Order
  -> Belongs to a Django CustomUser.
  -> Has many OrderItems.
  -> Tracks lifecycle status.

OrderItem
  -> Belongs to an Order.
  -> Belongs to a Product.
  -> Stores price snapshot and quantity.
```

---

# 12. Admin and Static Files

Django has admin and static support configured:

```text
/admin/
/static/
```

But the active Kong config currently exposes only:

```text
/api/auth
/api/products
/api/orders
/api/orders/webhook
/api/token
/orders/*
```

So `/admin/` and `/static/` are not currently exposed through Kong unless additional Kong routes are added.

---

# 13. Testing and API Scratch File

Testing framework:

```text
pytest
pytest-django
Django REST Framework APIClient
```

Important test files:

```text
users/tests.py
products/tests.py
orders/tests.py
pytest.ini
```

Current tests cover:

```text
User registration
Product creation
Successful order creation
Stock deduction
Insufficient stock rejection
```

API scratch/test file:

```text
api_tests.rest
```

Current note:

```text
api_tests.rest now uses:

http://127.0.0.1:8080
POST /api/auth/login
POST /api/auth/register
GET  /api/products/items/
POST /api/orders/
```

So the scratch file now matches the current Kong gateway setup for the main registration, login, catalog, and order flow.

---

# 14. Request Flow Summary

## User Registration Through Kong and FastAPI

```text
Client
  -> Kong /api/auth/register
  -> FastAPI /register
  -> PostgreSQL identity_users
  -> FastAPI internal call to Django /api/orders/users/sync/
  -> Django validates INTERNAL_CLUSTER_SECRET
  -> PostgreSQL users_customuser
```

---

## User Login Through Kong and FastAPI

```text
Client
  -> Kong /api/auth/login
  -> FastAPI /login
  -> FastAPI verifies password
  -> FastAPI returns JWT signed for Kong validation
```

---

## Authenticated Product or Order Request

```text
Client with Bearer token
  -> Kong /api/orders/*
  -> Kong validates JWT
  -> Django KongJWTAuthentication maps the verified identity to request.user
  -> Django view handles request
```

---

## Create Order

```text
Client with Bearer token
  -> Kong /api/orders/
  -> Kong JWT plugin validates token
  -> Django maps the verified token identity to request.user
  -> OrderSerializer transaction.atomic()
  -> Product row locked with select_for_update()
  -> Stock checked and deducted
  -> OrderItem rows created with price snapshots
  -> Celery task queued after commit
  -> Order returned
```

---

## Pay for Order

```text
Client with Bearer token
  -> Kong /api/orders/<id>/create-checkout-session/
  -> Django creates Stripe Checkout Session
  -> Client receives checkout_url
  -> User pays on Stripe
  -> Stripe calls /api/orders/webhook/
  -> Django verifies Stripe webhook signature
  -> Order marked paid
```

---

# 15. Current Strengths

```text
1. Kong is now the centralized API gateway.
2. Backend service ports are internal-only in Docker Compose.
3. JWT verification has moved to the edge gateway.
4. Django no longer needs to parse JWTs directly for protected gateway routes.
5. Django maps Kong-verified identity into request.user.
6. FastAPI includes an iss claim that matches the Kong JWT credential key.
7. INTERNAL_CLUSTER_SECRET separates internal service auth from public JWT auth.
8. Products and categories remain read-only at the Django view layer.
9. Order creation uses transaction.atomic().
10. Product stock rows are locked with select_for_update().
11. Product price is locked into OrderItem at purchase time.
12. Celery work is queued after transaction commit.
13. Stripe checkout and webhook verification are implemented.
14. Tests cover important stock and order behaviors.
```

---

# 16. Current Observations / Things To Revisit

## Kong Route Coverage

Kong currently exposes:

```text
/api/auth
/api/products
/api/orders
```

It does not expose:

```text
/admin/
/static/
/api/users/
/api/token/refresh/
```

That may be intentional, but the docs/API scratch file should match the actual public gateway routes.

---

## Product Catalog Auth Mismatch

Status:

```text
Fixed.
```

Django allows anonymous catalog access:

```text
permission_classes = [AllowAny]
```

Kong now exposes:

```text
/api/products
```

without the JWT plugin, so gateway behavior and Django behavior are aligned.

---

## Stripe Webhook JWT Exemption

Status:

```text
Fixed.
```

The webhook endpoint is:

```text
/api/orders/webhook/
```

Kong now defines a separate public route for:

```text
/api/orders/webhook
```

without JWT. Django still verifies the Stripe signature before changing any order status.

---

## JWT Secret Encoding Should Be Verified

FastAPI currently does:

```text
SECRET_KEY = bytes.fromhex(os.getenv("JWT_SECRET"))
```

Kong is configured with the JWT credential secret through Docker/Kong configuration.

Recommended check:

```text
Confirm Kong is verifying against the same raw bytes that FastAPI signs with, not the visible hex text itself.
```

---

## Celery Status Mismatch

Status:

```text
Fixed.
```

`orders/tasks.py` previously attempted to set:

```text
completed
```

But `Order.STATUS_CHOICES` currently contains:

```text
pending
paid
shipped
delivered
cancelled
```

Current behavior:

```text
The Celery task no longer changes order status.
It only simulates invoice generation and email dispatch.
```

Stripe remains responsible for changing orders from `pending` to `paid`.

---

## Duplicate Database Configuration

`config/settings.py` first builds `DATABASES` from environment variables, then later overwrites it with a hardcoded PostgreSQL config.

Current result:

```text
The hardcoded db/ecom_db/ecom_user configuration wins at runtime.
```

Recommended fix:

```text
Keep one DATABASES block, preferably the environment-driven one with sensible defaults.
```

---

## API Scratch File Is Current

Status:

```text
Fixed.
```

`api_tests.rest` now uses:

```text
http://127.0.0.1:8080
/api/auth/register
/api/auth/login
/api/products/items/
/api/orders/
```

Remaining note:

```text
The checkout example uses the legacy /orders/<id>/create-checkout-session/ path for compatibility with the API spec.
```

---

# 17. Final Simple Explanation

This backend currently works like this:

```text
Kong receives all public API traffic on port 8080.
FastAPI handles registration, login, password hashing, and JWT creation.
FastAPI syncs shadow users into Django through an internal secret.
Kong validates JWTs before protected requests reach Django.
Kong verifies protected requests before Django handles them.
Django maps the verified identity to request.user and handles ecommerce logic.
PostgreSQL stores identity users, Django users, products, orders, and order items.
Redis carries Celery jobs.
Celery performs background fulfillment/invoice/email simulation.
Stripe handles checkout payment.
Stripe webhooks update local order payment status after Django verifies the Stripe signature.
```

Main user journey:

```text
Register through /api/auth/register
  -> FastAPI creates identity user
  -> FastAPI syncs shadow user into Django
  -> Login through /api/auth/login
  -> Receive Kong-verifiable JWT
  -> Call protected Kong routes with Bearer token
  -> Kong verifies JWT before Django handles the request
  -> Django creates authenticated order
  -> Django locks stock and creates order safely
  -> Celery task starts after commit
  -> Create Stripe checkout session
  -> Pay on Stripe
  -> Stripe webhook marks order as paid
```

---

# 18. Latest Implementation Update

This section compares the current codebase against the last documented observations above.

The project has moved from "Kong migration with known follow-up items" to a cleaner gateway-first shape:

```text
Public client
  -> Kong :8080
     -> /api/auth/*             -> FastAPI Identity Service
     -> /api/products/*         -> Django catalog, public at gateway
     -> /api/orders/webhook/*   -> Django Stripe webhook, public at gateway
     -> /api/orders/*           -> Django orders, JWT protected
     -> /orders/*               -> Legacy checkout compatibility route, JWT protected
     -> /api/token/*            -> Django SimpleJWT compatibility route, public at gateway
```

## What Is Fixed

| Previous observation | Current state | Result |
| --- | --- | --- |
| Product catalog could require JWT at Kong even though Django allows public reads. | `gateway/kong.yml` now has `products-public-route` without the JWT plugin. | Product reads can be public through `/api/products/*`. |
| Stripe webhook could be blocked by Kong JWT because it lives under `/api/orders`. | `gateway/kong.yml` now defines `order-webhook-route` before the protected orders route and does not attach JWT. | Stripe can call `/api/orders/webhook/` while Django still verifies the Stripe signature. |
| Celery task tried to set an invalid `completed` status. | `orders/tasks.py` now leaves order status unchanged and only performs invoice/email simulation. | Payment state remains owned by Stripe webhook: `pending -> paid`. |
| `api_tests.rest` used old gateway/auth paths. | `api_tests.rest` now targets `http://127.0.0.1:8080`, `/api/auth/register`, `/api/auth/login`, `/api/products/items/`, and `/api/orders/`. | Manual API testing now matches the Kong-first runtime. |
| Internal sync reused a broad secret source. | FastAPI sends `INTERNAL_CLUSTER_SECRET`; Django reads `INTERNAL_CLUSTER_SECRET` through `decouple.config`. | Service-to-service sync is separated from JWT signing and Django `SECRET_KEY`. |
| Celery result handling was implicit. | `config/settings.py` now sets `CELERY_RESULT_SERIALIZER = json` and `CELERY_TIMEZONE = UTC`. | Worker result state tracking is more predictable and time handling is explicit. |

## What Changed

```text
Authentication boundary
  Before:
    Django directly decoded JWTs.

  Now:
    Kong is the edge verifier.
    Django trusts Kong headers when present.
    Django falls back to decoding JWT claims only after checking Kong's X-Consumer-Username marker.
```

```text
Gateway route model
  Public:
    /api/auth
    /api/products
    /api/orders/webhook
    /api/token

  Protected:
    /api/orders
    /orders/* legacy checkout path
```

```text
Order lifecycle
  pending
    -> Celery invoice/email simulation runs without changing payment status
    -> Celery stores task/result data using JSON serialization
    -> Stripe checkout is created
    -> Stripe webhook verifies payment
    -> paid
```

## Current Request Map

```text
Register
  Client -> Kong /api/auth/register
         -> FastAPI /register
         -> PostgreSQL identity_users
         -> Django /api/orders/users/sync/
         -> PostgreSQL users_customuser

Login
  Client -> Kong /api/auth/login
         -> FastAPI /login
         -> JWT with iss=ecom_identity_v1

Browse catalog
  Client -> Kong /api/products/items/
         -> Django products API
         -> PostgreSQL products_product

Create order
  Client + Bearer token -> Kong /api/orders/
                        -> Kong JWT plugin
                        -> Django KongJWTAuthentication
                        -> OrderSerializer transaction
                        -> Product row locks and stock deduction
                        -> Celery task after commit

Checkout
  Client + Bearer token -> Kong /api/orders/<id>/create-checkout-session/
                        -> Django Stripe Checkout session
                        -> Stripe hosted payment page

Webhook
  Stripe -> Kong /api/orders/webhook/
         -> Django Stripe signature verification
         -> Order marked paid
```

## Still Open / Worth Cleaning Next

| Area | Current note | Suggested direction |
| --- | --- | --- |
| Database settings | `config/settings.py` still defines `DATABASES` twice. The second hardcoded PostgreSQL block wins at runtime. | Keep one environment-driven `DATABASES` block with the build-mode SQLite fallback. |
| JWT secret handling | FastAPI signs with `JWT_SECRET` from the environment. Kong currently stores the same secret directly in `gateway/kong.yml`. | Move the Kong secret injection to deployment-time configuration or clearly document it as local-only. |
| Header mapping | Kong validates JWTs, but the route does not currently add `X-User-Email` / `X-User-Id` headers on `/api/orders`. Django can still decode claims after Kong verification. | Either add a Kong request-transformer for protected order routes or simplify Django auth around the current verified-token fallback. |
| Admin/static exposure | Django admin and static files exist, but Kong does not expose `/admin/` or `/static/`. | Keep internal-only if intentional, or add explicit Kong routes for admin workflows. |
| Legacy checkout route | `/orders/*` is supported for API spec compatibility. | Prefer `/api/orders/<id>/create-checkout-session/` as the canonical route and keep legacy only if clients still need it. |

## Clean Target Architecture

```text
Kong owns:
  - Public routing
  - JWT verification for protected APIs
  - Public exceptions for catalog and Stripe webhook routes

FastAPI owns:
  - Identity users
  - Password hashing
  - JWT creation
  - Shadow-user sync requests

Django owns:
  - Catalog data
  - Order creation
  - Stock integrity
  - Stripe checkout/webhook logic
  - Admin and business records

Redis/Celery own:
  - Background invoice/email simulation after order commit

PostgreSQL owns:
  - Identity users
  - Django shadow users
  - Catalog, orders, and order items
```
