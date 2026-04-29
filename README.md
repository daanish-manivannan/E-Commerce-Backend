# 🛒 E-Commerce Platform Backend

A **production-grade, scalable REST API** built using **Django**, **PostgreSQL**, and **Docker**, designed with a **Use Case–driven, Test-First development approach** to simulate real-world backend engineering practices.

---

## 🚀 Tech Stack

| Layer               | Technology                               |
| ------------------- | ---------------------------------------- |
| **Backend**         | Django 5, Django REST Framework          |
| **Database**        | PostgreSQL (Dockerized)                  |
| **Authentication**  | JWT (SimpleJWT), Custom Email-Based User |
| **Async Tasks**     | Celery + Redis                           |
| **Payments**        | Stripe API                               |
| **Testing**         | pytest, pytest-django                    |
| **Infrastructure**  | Docker, Docker Compose                   |
| **Static Handling** | WhiteNoise                               |

---

## ✨ Key Highlights

* 🔐 Secure **JWT Authentication** with custom user model
* 🧠 **Use Case–driven architecture (UC-based incremental builds)**
* 📦 Fully normalized **relational data modeling**
* ⚡ **Async background processing** (Invoices, Emails)
* 💳 **Stripe-integrated payment pipeline** with webhook verification
* 🐳 **Production-ready containerized deployment**
* 🧪 Strong **test coverage with pytest (TDD approach)**

---

## 📈 Phase-wise Development (Engineering Journey)

### 🏗️ Phase 1: Infrastructure & Foundation

**Goal:** Establish a production-like development environment

* Dockerized **PostgreSQL setup**
* Clean **MVT architecture**
* Modular Django project structure

---

### 🔐 Phase 2: Authentication & Access Control

**Goal:** Build secure identity management

* Custom **Email-based User Model**
* JWT Authentication using SimpleJWT
* Registration & login APIs

---

### 📦 Phase 3: Core Business Logic & Checkout Engine

**Goal:** Design scalable e-commerce logic

* Models: `Category`, `Product`, `Order`, `OrderItem`
* DRF **ModelViewSets + Routers** for CRUD
* Checkout system with:

  * 🧾 Price locking at purchase time
  * 📉 Dynamic stock validation
* 🧪 Automated tests:

  * Inventory boundaries
  * Auth-based access control

---

### ⚡ Phase 4: Asynchronous Processing *(Completed)*

**Goal:** Improve performance via background jobs

* Integrated **Redis + Celery**
* Automated:

  * PDF invoice generation
  * Email dispatch system

---

### 💳 Phase 5: Payment Integration *(Completed)*

**Goal:** Build secure fintech layer

* Stripe Checkout integration
* Secure webhook handling with signature verification
* Order status lifecycle (`Pending → Paid`)

---

### 🐳 Phase 6: Production Hardening *(Completed)*

**Goal:** Prepare for real-world deployment

* Multi-stage Docker builds
* Service orchestration (Web, DB, Redis, Workers)
* Health checks & dependency management

---

### 📊 Phase 7: Observability & Logging *(Completed)*

**Goal:** Enable monitoring & debugging

* Structured logging (INFO / ERROR separation)
* Container-level log tracking
* System verification workflows

---

## ⚙️ Local Development Setup

### 1️⃣ Environment Variables

Create `.env` file:

```env
STRIPE_PUBLIC_KEY=pk_test_...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
DJANGO_SECRET_KEY=your_secret_key
```

---

### 2️⃣ Run with Docker (Recommended)

```bash
docker-compose up --build -d
```

---

### 3️⃣ Initialize Database

```bash
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
```

---

## 🔗 API Overview

### 🔐 Authentication

* `POST /api/token/` → Get JWT tokens
* `POST /api/token/refresh/` → Refresh token
* `POST /api/users/register/` → Register user

---

### 📦 Catalog

* `GET /products/categories/` → List categories
* `GET /products/items/` → List products

---

### 🧾 Orders (Auth Required)

* `GET /api/orders/` → Order history
* `POST /api/orders/` → Create order

---

### 💳 Payments

* `POST /api/orders/<id>/create-checkout-session/` → Stripe checkout
* `POST /api/orders/webhook/` → Payment confirmation (Stripe)

---

## 🧪 Testing

Run test suite:

```bash
docker-compose exec web pytest
```

✔ Covers:

* Inventory validation
* Authentication rules
* Order access restrictions

---

## 🛠️ Monitoring & Logs

```bash
docker-compose logs -f web worker
docker ps
```

---

## 🧠 Architectural Strengths

* 📌 **Use Case (UC)-based development** → structured, incremental delivery
* 🔄 **TDD-first approach** → reliable & maintainable code
* ⚡ **Async task delegation** → improved API performance
* 🔐 **Secure payment workflows** → production-grade practices
* 🐳 **Container-first design** → deployment-ready

---

## 📌 Future Enhancements

* CI/CD pipeline (GitHub Actions)
* Role-based access control (RBAC)
* Product search & filtering (ElasticSearch)
* Caching layer optimization
* Frontend integration (React / Next.js)

---
## ⭐ Why This Project Stands Out

This isn’t just a CRUD app — it demonstrates:

* Real-world backend architecture
* Production-grade system design
* End-to-end feature ownership (Auth → Orders → Payments → Deployment)
* Strong alignment with **SDE1 backend expectations**
