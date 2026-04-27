# E-Commerce Platform Backend

A production-quality REST API built with Django and PostgreSQL, following a strict Use Case-based incremental development roadmap.

## 🚀 Tech Stack
* **Framework:** Django 5.x, Django REST Framework (DRF)
* **Database:** PostgreSQL 15 (Containerized)
* **Authentication:** SimpleJWT (JSON Web Tokens), Custom Email-Based User Model
* **Testing:** pytest & pytest-django
* **Environment:** Python 3.13, Docker

## 📈 Roadmap Progress
- [x] **Phase 1: Django Fundamentals + Setup**
  - Configured PostgreSQL via Docker Compose.
  - Established MVT architecture with the `products` app.
  - Customized the Django Admin interface.
  - Wrote automated database tests using `pytest-django`.
- [x] **Phase 2: Auth, Permissions & DRF**
  - Built `CustomUser` model (Email-based login via `AbstractBaseUser`).
  - Installed and configured Django REST Framework.
  - Implemented JWT Authentication (`/api/token/`).
  - Created API user registration endpoint with DRF Serializers.
  - Automated testing for auth endpoints.
- [ ] **Phase 3: Core Models + REST API**
- [ ] **Phase 4: Celery, Redis, S3 & PDF**
- [ ] **Phase 5: Stripe Payments + Webhooks**
- [ ] **Phase 6: Docker, CI/CD & Deployment**

## 💻 Local Development Setup

### 1. Environment Activation
```bash
# Activate the virtual environment
.\venv\Scripts\activate