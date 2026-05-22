# E-Commerce Backend Project Overview

This project is an ecommerce backend built with a small microservice-style architecture.

In simple terms:

**FastAPI handles login and registration. Django handles products, orders, payments, admin, and business logic. PostgreSQL stores the data. Redis and Celery handle background jobs. Stripe handles payments. Nginx acts as the front door.**

---

# 1. High-Level Architecture

```text
Client / Frontend
      |
      v
Nginx Gateway :80
      |
      |-- /auth/*  -> FastAPI Identity Service :8001
      |
      |-- /api/*   -> Django Order & Catalog Service :8000
      |
      |-- /admin/* -> Django Admin
              |
              v
        PostgreSQL Database
              |
              v
        Redis + Celery Workers
```

---

# 2. Main Services

## Nginx Gateway

File:

```text
gateway/nginx.conf
```

Nginx receives incoming requests and forwards them to the correct backend service.

Current routing:

```text
/auth/  -> Identity Service
/api/   -> Order & Catalog Service
/admin/ -> Django Admin
```

So the client does not need to know which backend service handles what. It talks to one gateway.

---

## Identity Service

Folder:

```text
Identity Service/
```

Technology:

```text
FastAPI + SQLAlchemy + PostgreSQL + JWT
```

Purpose:

```text
Handles user registration, login, password hashing, and JWT token creation.
```

Important files:

```text
main.py        -> FastAPI routes
models.py      -> Identity user database model
schemas.py     -> Request/response validation
auth_utils.py  -> Password hashing and JWT creation
database.py    -> Database connection
```

---

## Order & Catalog Service

Folder:

```text
Order & Catalog Service/
```

Technology:

```text
Django + Django REST Framework + PostgreSQL + Celery + Stripe
```

Purpose:

```text
Handles products, categories, users inside Django, orders, stock deduction, Stripe checkout, webhooks, admin, and async invoice/email jobs.
```

Important apps:

```text
users/     -> Django custom user / shadow user
products/  -> Categories and products
orders/    -> Orders, order items, checkout, Stripe webhook
config/    -> Django settings, URLs, Celery config, JWT auth
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
redis             -> Redis message broker
order-service     -> Django API
order_worker      -> Celery worker
order_beat        -> Celery beat scheduler
identity_service  -> FastAPI auth service
gateway           -> Nginx reverse proxy
```

---

# 4. Authentication Flow

## Registration Flow

Endpoint:

```text
POST /auth/register
```

Flow:

```text
1. User sends email and password to FastAPI.
2. FastAPI checks if the email already exists.
3. Password is hashed using bcrypt.
4. User is saved in the Identity Service table.
5. FastAPI calls Django internally.
6. Django creates a matching shadow user.
7. User registration completes.
```

Why shadow user exists:

```text
FastAPI owns real authentication and passwords.

Django still needs a local user row so orders can be linked to a user.

So Django creates a shadow user with the same email but no usable password.
```

---

## Login Flow

Endpoint:

```text
POST /auth/login
```

Flow:

```text
1. User sends email and password.
2. FastAPI finds the user.
3. FastAPI verifies the password.
4. FastAPI creates a JWT access token.
5. Client stores the token.
6. Client sends the token to Django APIs using:

Authorization: Bearer <token>
```

---

## Django JWT Validation

File:

```text
Order & Catalog Service/config/authentication.py
```

Flow:

```text
1. Django receives request with Bearer token.
2. Django decodes JWT using shared secret.
3. Django reads email from token subject.
4. Django gets or creates a local CustomUser.
5. Request is treated as authenticated.
```

---

# 5. Product / Catalog Flow

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

Endpoints are generated using Django REST Framework routers.

Main routes:

```text
/products/categories/
/products/items/
```

Permissions:

```text
Anyone can read products/categories.
Only authenticated users can create, update, or delete.
```

Simple explanation:

```text
Categories group products.
Products contain price and stock.
Only active products and categories are shown.
```

---

# 6. Order Flow

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

Order statuses:

```text
pending
paid
shipped
delivered
cancelled
```

Endpoint:

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

Flow:

```text
1. User sends products and quantities.
2. Django checks if user is authenticated.
3. Django checks whether every product has enough stock.
4. If stock is insufficient, order is rejected.
5. If stock is available, Django creates the order.
6. Django reduces product stock.
7. Django creates order items.
8. Product price is copied into OrderItem.price.
9. Celery background task is triggered.
10. API returns the created order.
```

Important business rule:

```text
Price is locked at purchase time.

If product price changes later, old orders remain correct because each OrderItem stores its own price.
```

---

# 7. Payment Flow

Payment provider:

```text
Stripe
```

Files:

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
1. User selects an existing pending order.
2. Django checks that order belongs to the current user.
3. Django checks that order status is pending.
4. Django converts order items into Stripe line items.
5. Django creates a Stripe Checkout Session.
6. Stripe returns a checkout URL.
7. Client redirects user to Stripe.
```

---

## Stripe Webhook Flow

Endpoint:

```text
POST /api/orders/webhook/
```

Flow:

```text
1. Stripe sends payment event to Django.
2. Django verifies Stripe webhook signature.
3. Django checks event type.
4. If event is checkout.session.completed:
   - Django reads order ID from client_reference_id.
   - Django finds the order.
   - If order is pending, Django marks it as paid.
5. Django returns HTTP 200 to Stripe.
```

Simple explanation:

```text
The user pays on Stripe.
Stripe tells Django payment succeeded.
Django updates the order from pending to paid.
```

---

# 8. Background Task Flow

Files:

```text
orders/tasks.py
config/celery.py
```

Technology:

```text
Celery + Redis
```

Triggered after:

```text
Order creation
```

Flow:

```text
1. Django creates order.
2. Django sends task to Redis.
3. Celery worker receives task.
4. Celery simulates invoice generation.
5. Celery simulates sending email.
```

Current task:

```text
fulfill_and_send_invoice_task(order_id)
```

Simple explanation:

```text
Slow work is moved outside the API request.

The user gets a fast response, while invoice/email work happens in the background.
```

---

# 9. Database Design

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
  -> Used for real login/password in FastAPI

Django CustomUser
  -> Used by Django to link orders to a user

Category
  -> Has many Products

Product
  -> Belongs to Category
  -> Has many OrderItems

Order
  -> Belongs to User
  -> Has many OrderItems

OrderItem
  -> Belongs to Order
  -> Belongs to Product
```

---

# 10. Admin Flow

Django admin route:

```text
/admin/
```

Admin can manage:

```text
Users
Categories
Products
Orders
Order Items
```

Admin configuration files:

```text
users/admin.py
products/admin.py
orders/admin.py
```

Simple explanation:

```text
Admin is used by internal staff/developers to inspect and manage backend data.
```

---

# 11. Testing

Testing framework:

```text
pytest
pytest-django
Django REST Framework APIClient
```

Important files:

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

Example tested behavior:

```text
If product stock is 10 and user buys 2, stock becomes 8.

If user tries to buy 20 while only 10 exist, order is rejected and stock remains 10.
```

---

# 12. Request Flow Summary

## User Registration

```text
Client
  -> Nginx /auth/register
  -> FastAPI Identity Service
  -> PostgreSQL identity_users
  -> Django internal user sync
  -> PostgreSQL users_customuser
```

---

## User Login

```text
Client
  -> Nginx /auth/login
  -> FastAPI Identity Service
  -> JWT token returned
```

---

## View Products

```text
Client
  -> Django Product API
  -> PostgreSQL products_product
  -> Product list returned
```

---

## Create Order

```text
Client with JWT
  -> Django /api/orders/
  -> JWT validated
  -> Stock checked
  -> Order created
  -> Stock deducted
  -> Celery task queued
  -> Order returned
```

---

## Pay for Order

```text
Client
  -> Django create-checkout-session
  -> Stripe Checkout Session created
  -> Checkout URL returned
  -> User pays on Stripe
  -> Stripe webhook calls Django
  -> Order marked as paid
```

---

# 13. Strengths of the Project

```text
1. Clear separation between identity and commerce logic.
2. JWT-based authentication.
3. Product price locking inside order items.
4. Stock validation before order creation.
5. Stripe checkout integration.
6. Stripe webhook signature verification.
7. Async background task processing with Celery.
8. Dockerized multi-service setup.
9. PostgreSQL used instead of SQLite.
10. Tests for important business rules.
```

---

# 14. Important Observations

## JWT Secret Wiring

Django JWT authentication reads:

```text
JWT_SECRET
```

But `docker-compose.yml` passes:

```text
SECRET_KEY=${SHARED_JWT_SECRET}
```

This may cause FastAPI tokens to fail in Django unless `JWT_SECRET` is also passed to Django.

---

## Product Route Gateway Issue

Django mounts products at:

```text
/products/
```

Nginx forwards:

```text
/api/
/admin/
/auth/
```

So product endpoints may not be reachable through the gateway unless Nginx is updated or products are moved under `/api/products/`.

---

## Secrets in .env

The `.env` file contains Stripe test keys and webhook secret.

Even though they are test keys, they should be rotated if the project is shared publicly.

---

# 15. Final Simple Explanation

This backend works like this:

```text
FastAPI handles identity.
Django handles ecommerce.
PostgreSQL stores everything.
Redis passes background jobs to Celery.
Celery handles slow work like invoices and emails.
Stripe handles payment.
Nginx routes traffic to the right service.
```

The main user journey is:

```text
Register
  -> Login
  -> Get JWT
  -> Browse products
  -> Create order
  -> Stock is deducted
  -> Invoice/email task starts
  -> Create Stripe checkout
  -> Pay
  -> Stripe webhook marks order as paid
```
