# E-Commerce Platform Backend

A production-quality REST API built with Django and PostgreSQL, following a strict Use Case-based incremental development roadmap.

## 🚀 Tech Stack & Architecture
* **Framework:** Django 5.x, Django REST Framework (DRF)
* **Database:** PostgreSQL 15 (Containerized)
* **Authentication:** SimpleJWT, Custom Email-Based User Model, Session Auth (for Admin/Browsable API)
* **Relational Data:** ForeignKey relationships (Products -> Categories, Orders -> Users/Products)
* **Testing:** pytest, pytest-django, DRF APIClient
* **Environment:** Python 3.13, Docker

## 📈 Roadmap Progress
- [x] **Phase 1: Django Fundamentals + Setup**
  - Configured PostgreSQL via Docker Compose.
  - Established MVT architecture.
- [x] **Phase 2: Auth, Permissions & DRF**
  - Built `CustomUser` model (Email-based login).
  - Implemented JWT Authentication and Registration API.
- [x] **Phase 3: Core Models + REST API**
  - Designed relational database schema (`Category`, `Product`, `Order`, `OrderItem`).
  - Implemented DRF `ModelViewSets` and `DefaultRouters` for automated CRUD operations.
  - Built secure Checkout Engine (Nested Serializers, dynamic stock deduction, price locking).
  - Wrote automated test suites for inventory boundary limits and authentication rules.
- [ ] **Phase 4: Celery, Redis, S3 & PDF**
- [ ] **Phase 5: Stripe Payments + Webhooks**
- [ ] **Phase 6: Docker, CI/CD & Deployment**


## 💻 Local Development Setup

### 1. Environment Activation
```bash
# Activate the virtual environment
.\venv\Scripts\activate
```

```markdown
## 💻 Local Development Setup

### 1. Environment Activation
```bash
# Activate the virtual environment
.\venv\Scripts\activate
```

### 2. Database Initialization
Ensure Docker Desktop is running, then start the PostgreSQL container:
```bash
docker-compose up -d
```

### 3. Run the Server
```bash
python manage.py runserver
```

### 4. Key API Endpoints
**Authentication**
* `POST /api/token/` - Get JWT Access & Refresh Tokens
* `POST /api/token/refresh/` - Get a new Access Token
* `POST /api/users/register/` - Register a new customer

**Catalog (Read/Write)**
* `GET /products/categories/` - List all active categories
* `GET /products/items/` - List all active products

**Checkout & Orders (Requires Authentication)**
* `GET /api/orders/` - List the logged-in user's order history
* `POST /api/orders/` - Submit a new order (JSON payload requires `items` array with `product` ID and `quantity`)

### 5. Running the Test Suite
To execute the automated tests and verify inventory logic and database integrity:
```bash
pytest
```