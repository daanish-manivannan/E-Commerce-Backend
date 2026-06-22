# GEMINI.md

## Project Overview
This project is a containerized e-commerce backend platform built using a microservice-oriented architecture. It separates identity management from core commerce logic (catalog and orders) and uses an API Gateway to secure and route traffic.

### Core Architecture
- **API Gateway (Kong):** The public entry point (`http://127.0.0.1:8080`). Handles routing, edge-level JWT verification, rate limiting, and request size limiting.
- **Identity Service (FastAPI):** Manages user credentials, authentication (registration, login, logout, refresh), email verification, and password resets. It acts as the source of truth for user identity and issues HS256 JWT tokens.
- **Order & Catalog Service (Django REST Framework):** Manages the product catalog and order lifecycle. It uses "shadow users" synced from the Identity Service to maintain data integrity while delegating auth.
- **Background Work (Celery):** Handles asynchronous tasks like email simulation and invoice generation, backed by **Redis**.
- **Database (PostgreSQL):** Persistent storage for both Identity and Commerce services.
- **Payments (Stripe):** Integrated for Checkout sessions and Webhook-based payment confirmation.

### Tech Stack
- **Languages:** Python 3.11
- **Frameworks:** FastAPI, Django REST Framework
- **Databases:** PostgreSQL 15, Redis 7
- **Tools:** Kong 3.4, Celery, Docker, Docker Compose
- **Quality:** Ruff, Black, Isort, Mypy, Pytest

---

## Building and Running

### Prerequisites
- Docker and Docker Compose
- Python 3.11 (for local linting/type checking)
- A `.env` file in the root (see `README.md` for required variables)

### Common Commands

| Action | Command |
| --- | --- |
| **Start full stack** | `docker-compose up --build` |
| **Stop full stack** | `docker-compose down` |
| **Run Migrations** | `docker-compose exec order-service python manage.py migrate` |
| **Create Admin** | `docker-compose exec order-service python manage.py createsuperuser` |
| **Generate Kong Config**| `make kong-config` (uses `JWT_SECRET` from `.env`) |
| **Reload Kong** | `make kong-reload` |
| **View Logs** | `docker-compose logs -f` |

### Environment Setup
Create a `.env` file based on the template in `README.md`. Ensure `JWT_SECRET` and `INTERNAL_CLUSTER_SECRET` match across services.

---

## Development Conventions

### Coding Style & Quality
The project enforces strict coding standards using the following tools:
- **Linting:** `ruff check .`
- **Formatting:** `black .` and `isort .`
- **Type Checking:** `mypy .` (Type hints are required; `disallow_untyped_defs = true` is enabled).
- **Pre-commit:** Hooks are configured to run these checks before every commit.

### Testing
- **Django Tests:** Run via `docker-compose exec order-service pytest`.
- **Gateway Tests:** Run `python gateway_test.py` locally to verify Kong routing and security.
- **Manual Testing:** Use `api_tests.rest` with the VS Code REST Client or similar tools.

### Architectural Rules
1. **Identity vs. Commerce:** Never store user passwords in the Django service. Django should only store "shadow users" (email and status) for record ownership.
2. **Auth Boundary:** Kong is the security boundary. Protected routes in Django must check for the `X-Consumer-Username: identity-service` header (injected by Kong after successful JWT verification) before trusting the `X-User-Email` or token claims.
3. **Transactional Integrity:** Use `select_for_update()` when checking/deducting stock in Django to prevent race conditions.
4. **Async Side Effects:** Always dispatch Celery tasks using `transaction.on_commit()` to ensure they only run if the database transaction succeeds.
5. **Logging:** Both services use structured JSON logging to stdout for compatibility with log aggregators. Use `logger.info()`, `logger.error()`, etc., with extra context as needed.

### Project Structure
- `Identity Service/`: FastAPI identity microservice.
- `Order & Catalog Service/`: Django ecommerce microservice.
- `gateway/`: Kong declarative configuration templates.
- `monitoring/`: Prometheus configuration.
- `api_tests.rest`: Live API documentation/test suite.
