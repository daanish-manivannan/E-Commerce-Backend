# E-Commerce Platform Backend

A production-quality REST API built with Django and PostgreSQL, following a strict Use Case-based incremental development roadmap.

## 🚀 Tech Stack (Phase 1)
* **Framework:** Django 5.x
* **Database:** PostgreSQL 15 (Containerized)
* **Testing:** pytest & pytest-django
* **Environment:** Python 3.13, Docker

## 📈 Roadmap Progress
- [x] **Phase 1: Django Fundamentals + Setup**
  - Configured PostgreSQL via Docker Compose (no SQLite).
  - Established MVT architecture with the `products` app.
  - Customized the Django Admin interface (`list_display`, `search_fields`).
  - Wrote automated database tests using `pytest-django`.
- [ ] **Phase 2: Auth, Permissions & DRF**
- [ ] **Phase 3: Core Models + REST API**
- [ ] **Phase 4: Celery, Redis, S3 & PDF**
- [ ] **Phase 5: Stripe Payments + Webhooks**
- [ ] **Phase 6: Docker, CI/CD & Deployment**

## 💻 Local Development Setup

### 1. Environment Activation
```bash
# Activate the virtual environment
.\venv\Scripts\activate