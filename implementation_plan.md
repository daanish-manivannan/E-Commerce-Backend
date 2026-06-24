# Railway Deployment — Implementation Plan

## Goal
Deploy the full ECom backend to Railway, preserving the complete architecture:
Kong → Identity Service (FastAPI) → Order Service (Django) → Celery Worker + Beat → PostgreSQL + Redis

---

## Railway Services Map

| Railway Service | Source | Root Directory |
|---|---|---|
| `postgres` | Railway Plugin | — |
| `redis` | Railway Plugin | — |
| `identity-service` | GitHub repo | `Identity Service/` |
| `order-service` | GitHub repo | `Order & Catalog Service/` |
| `celery-worker` | GitHub repo | `Order & Catalog Service/` (different start cmd) |
| `celery-beat` | GitHub repo | `Order & Catalog Service/` (different start cmd) |
| `gateway` | GitHub repo | `gateway/` |

**Deployment order**: postgres → redis → order-service → identity-service → celery-worker → celery-beat → gateway

---

## Proposed Changes

### Component 1 — Identity Service

#### [MODIFY] [main.py](file:///d:/Projects/Django%20Project/ECom/Identity%20Service/main.py)

The ORDER_SERVICE_SYNC_URL is hardcoded to the Docker Compose hostname `order-service:8000`. On Railway, internal services are reachable via `<service-name>.railway.internal`. Make it configurable via env var.

**Line 54 — change:**
```diff
- ORDER_SERVICE_SYNC_URL = "http://order-service:8000/api/orders/users/sync/"
+ ORDER_SERVICE_SYNC_URL = config(
+     "ORDER_SERVICE_SYNC_URL",
+     default="http://order-service:8000/api/orders/users/sync/",
+ )
```

#### [MODIFY] [railway.toml](file:///d:/Projects/Django%20Project/ECom/Identity%20Service/railway.toml)

Already correct. Just verify it matches:
```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health/identity"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

---

### Component 2 — Order & Catalog Service (Django)

#### [MODIFY] [railway.toml](file:///d:/Projects/Django%20Project/ECom/Order%20&%20Catalog%20Service/railway.toml)

Add `migrate` before starting gunicorn so Railway runs migrations automatically on every deploy:

```diff
- startCommand = "gunicorn --bind 0.0.0.0:$PORT config.wsgi:application --workers 2 --timeout 120"
+ startCommand = "python manage.py migrate --no-input && python manage.py collectstatic --no-input && gunicorn --bind 0.0.0.0:$PORT config.wsgi:application --workers 2 --timeout 120"
```

#### [MODIFY] [production.py](file:///d:/Projects/Django%20Project/ECom/Order%20&%20Catalog%20Service/config/settings/production.py)

Two critical fixes:
1. Railway injects a single `DATABASE_URL` — current code expects 4 separate POSTGRES_* vars
2. `SECURE_SSL_REDIRECT = True` causes redirect loops on Railway (Railway terminates TLS at its load balancer; Django sees plain HTTP internally)

```diff
  import os as _os

+ import dj_database_url
  from config.env_validator import validate_required_env_vars
  from decouple import config
  from .base import *  # noqa: F401, F403

  validate_required_env_vars()

  DEBUG = False

  ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

  _railway_domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
  if _railway_domain:
      ALLOWED_HOSTS.append(_railway_domain)
      CSRF_TRUSTED_ORIGINS = [f"https://{_railway_domain}"]

- # Database configuration for production
- DATABASES = {
-     "default": {
-         "ENGINE": "django.db.backends.postgresql",
-         "NAME": config("POSTGRES_DB"),
-         "USER": config("POSTGRES_USER"),
-         "PASSWORD": config("POSTGRES_PASSWORD"),
-         "HOST": config("POSTGRES_HOST", default="db"),
-         "PORT": config("POSTGRES_PORT", default="5432"),
-         "CONN_MAX_AGE": 600,
-         "OPTIONS": {
-             "connect_timeout": 10,
-         },
-     }
- }
+ # Database — Railway injects DATABASE_URL automatically via its Postgres plugin
+ _db_url = _os.environ.get("DATABASE_URL")
+ if _db_url:
+     DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=600)}
+ else:
+     DATABASES = {
+         "default": {
+             "ENGINE": "django.db.backends.postgresql",
+             "NAME": config("POSTGRES_DB"),
+             "USER": config("POSTGRES_USER"),
+             "PASSWORD": config("POSTGRES_PASSWORD"),
+             "HOST": config("POSTGRES_HOST", default="db"),
+             "PORT": config("POSTGRES_PORT", default="5432"),
+             "CONN_MAX_AGE": 600,
+             "OPTIONS": {"connect_timeout": 10},
+         }
+     }

- SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=True, cast=bool)
+ # Railway handles TLS at its load balancer; Django sees plain HTTP internally.
+ # Setting this True causes an infinite redirect loop on Railway.
+ SECURE_SSL_REDIRECT = False
+ # Tell Django to trust Railway's forwarded protocol header
+ SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
  SESSION_COOKIE_SECURE = True
  CSRF_COOKIE_SECURE = True
  SECURE_HSTS_SECONDS = 31536000
  SECURE_HSTS_INCLUDE_SUBDOMAINS = True
  SECURE_HSTS_PRELOAD = True
```

#### [MODIFY] [base.py](file:///d:/Projects/Django%20Project/ECom/Order%20&%20Catalog%20Service/config/settings/base.py)

Railway injects `REDIS_URL` automatically. Celery and the cache must read from it instead of the hardcoded Docker Compose hostname `redis`:

```diff
- CELERY_BROKER_URL = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
- CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/0")
+ _redis_base = os.environ.get("REDIS_URL", "redis://redis:6379/0")
+ CELERY_BROKER_URL = config("CELERY_BROKER_URL", default=_redis_base)
+ CELERY_RESULT_BACKEND = config("CELERY_RESULT_BACKEND", default=_redis_base)
```

```diff
  CACHES = {
      "default": {
          "BACKEND": "django.core.cache.backends.redis.RedisCache",
-         "LOCATION": os.environ.get("REDIS_URL", "redis://redis:6379/2"),
+         "LOCATION": os.environ.get("REDIS_CACHE_URL", os.environ.get("REDIS_URL", "redis://redis:6379/2")),
          "OPTIONS": {
              "db": "2",
          },
```

#### [MODIFY] [requirements.txt](file:///d:/Projects/Django%20Project/ECom/Order%20&%20Catalog%20Service/requirements.txt)

Add two dependencies:

```diff
  # Infrastructure
  whitenoise==6.12.0
+ gunicorn==23.0.0
+ dj-database-url==2.3.0
```

#### [MODIFY] [env_validator.py](file:///d:/Projects/Django%20Project/ECom/Order%20&%20Catalog%20Service/config/env_validator.py)

Remove `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` from required vars — Railway provides `DATABASE_URL` as a single connection string instead:

```diff
  REQUIRED_VARS = {
      "SECRET_KEY": "Django internal secret key",
      "JWT_SECRET": "Shared JWT secret for auth services",
-     "POSTGRES_DB": "PostgreSQL database name",
-     "POSTGRES_USER": "PostgreSQL user account",
-     "POSTGRES_PASSWORD": "PostgreSQL password",
      "STRIPE_PUBLIC_KEY": "Stripe publishable key",
      "STRIPE_SECRET_KEY": "Stripe secret key",
      "STRIPE_WEBHOOK_SECRET": "Stripe webhook secret",
  }
```

---

### Component 3 — Celery Worker & Beat (No new files needed)

The Celery Worker and Beat use the **same Dockerfile** as the Order Service. In Railway, you'll deploy them as separate services pointing to the same root directory (`Order & Catalog Service/`) with a custom `startCommand` set directly in the Railway dashboard — no extra `railway.toml` files needed.

| Service | Start Command (set in Railway dashboard) |
|---|---|
| `celery-worker` | `celery -A config worker --loglevel=info --concurrency=2` |
| `celery-beat` | `celery -A config beat --loglevel=info` |

> [!NOTE]
> Both services share all environment variables from the order-service Railway environment — link them to the same Railway environment in the dashboard.

---

### Component 4 — Kong API Gateway

#### [NEW] `gateway/Dockerfile`

Kong needs a startup script to generate `kong.yml` from `kong.template.yml` at container start (injecting `KONG_JWT_SECRET`):

```dockerfile
FROM kong:3.4

USER root

# Install envsubst for template rendering
RUN apt-get update && apt-get install -y gettext-base && rm -rf /var/lib/apt/lists/*

# Copy the template and entrypoint
COPY kong.template.yml /usr/local/kong/kong.template.yml
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

USER kong
ENTRYPOINT ["/docker-entrypoint.sh"]
```

#### [NEW] `gateway/docker-entrypoint.sh`

```bash
#!/bin/sh
set -e

# Generate kong.yml by substituting KONG_JWT_SECRET at container startup.
# This keeps the JWT secret out of the repository entirely.
envsubst '$KONG_JWT_SECRET' < /usr/local/kong/kong.template.yml > /usr/local/kong/kong.yml

echo "✅ Kong config generated from template"

# Hand off to Kong's official entrypoint
exec kong docker-start
```

#### [MODIFY] [kong.template.yml](file:///d:/Projects/Django%20Project/ECom/gateway/kong.template.yml)

Update upstream URLs from Docker Compose service names to Railway private network hostnames:

```diff
  services:
    - name: identity-service
-     url: http://identity_service:8001
+     url: http://identity-service.railway.internal:8001

    - name: order-service
-     url: http://order-service:8000
+     url: http://order-service.railway.internal:8000
```

#### [NEW] `gateway/railway.toml`

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile"

[deploy]
startCommand = ""
healthcheckPath = "/"
healthcheckTimeout = 60
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

---

## Railway Dashboard Setup — Step by Step

### Step 1 — Create Project
1. Go to [railway.app](https://railway.app) → New Project → Empty Project
2. Name it `ECom`

### Step 2 — Add Managed Infrastructure
1. Click **+ New** → **Database** → **PostgreSQL** → Deploy
2. Click **+ New** → **Database** → **Redis** → Deploy
3. Both auto-generate connection URLs

### Step 3 — Deploy Order Service (runs migrations)
1. Click **+ New** → **GitHub Repo** → select your repo
2. Set **Root Directory**: `Order & Catalog Service`
3. Set **Service Name**: `order-service`
4. Add environment variables (see table below)
5. Deploy — watch logs for `migrate` step completing

### Step 4 — Deploy Identity Service
1. Click **+ New** → **GitHub Repo** → same repo
2. Set **Root Directory**: `Identity Service`
3. Set **Service Name**: `identity-service`
4. Add environment variables (see table below)
5. Deploy

### Step 5 — Deploy Celery Worker
1. Click **+ New** → **GitHub Repo** → same repo
2. Set **Root Directory**: `Order & Catalog Service`
3. Set **Service Name**: `celery-worker`
4. Go to **Settings** → **Deploy** → **Custom Start Command**:
   `celery -A config worker --loglevel=info --concurrency=2`
5. Copy all env vars from order-service
6. Deploy

### Step 6 — Deploy Celery Beat
1. Click **+ New** → **GitHub Repo** → same repo
2. Set **Root Directory**: `Order & Catalog Service`
3. Set **Service Name**: `celery-beat`
4. Go to **Settings** → **Deploy** → **Custom Start Command**:
   `celery -A config beat --loglevel=info`
5. Copy all env vars from order-service
6. Deploy

### Step 7 — Deploy Kong Gateway (last — needs internal URLs of above)
1. Click **+ New** → **GitHub Repo** → same repo
2. Set **Root Directory**: `gateway`
3. Set **Service Name**: `gateway`
4. Add environment variables (see table below)
5. Deploy

---

## Environment Variables — Per Service

### PostgreSQL Plugin (auto-injected by Railway)
Railway injects `DATABASE_URL`, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` automatically. No manual setup needed.

### Redis Plugin (auto-injected by Railway)
Railway injects `REDIS_URL` automatically.

### `identity-service` Variables
| Variable | Value |
|---|---|
| `DATABASE_URL` | Link to Postgres plugin (auto) |
| `REDIS_URL` | Link to Redis plugin (auto) |
| `JWT_SECRET` | Your 64-char HS256 secret |
| `INTERNAL_CLUSTER_SECRET` | Your cluster handshake secret |
| `ORDER_SERVICE_SYNC_URL` | `http://order-service.railway.internal:8000/api/orders/users/sync/` |

### `order-service` Variables
| Variable | Value |
|---|---|
| `DATABASE_URL` | Link to Postgres plugin (auto) |
| `REDIS_URL` | Link to Redis plugin (auto) |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `SECRET_KEY` | Your Django secret key |
| `JWT_SECRET` | Same as identity-service |
| `INTERNAL_CLUSTER_SECRET` | Same as identity-service |
| `STRIPE_PUBLIC_KEY` | From Stripe dashboard |
| `STRIPE_SECRET_KEY` | From Stripe dashboard |
| `STRIPE_WEBHOOK_SECRET` | From Stripe dashboard (after updating webhook URL) |
| `DEBUG` | `False` |

### `celery-worker` + `celery-beat` Variables
Copy all env vars from `order-service` exactly.

### `gateway` Variables
| Variable | Value |
|---|---|
| `KONG_JWT_SECRET` | Same value as `JWT_SECRET` |
| `KONG_DATABASE` | `off` |
| `KONG_DECLARATIVE_CONFIG` | `/usr/local/kong/kong.yml` |
| `KONG_PROXY_ACCESS_LOG` | `/dev/stdout` |
| `KONG_PROXY_ERROR_LOG` | `/dev/stderr` |
| `KONG_ADMIN_LISTEN` | `off` |

---

## Stripe Webhook — Post-Deploy Step

After the gateway is live, update your Stripe Dashboard webhook URL:

```
Old (local):  http://localhost:8080/api/orders/webhook/
New (Railway): https://<gateway-railway-domain>/api/orders/webhook/
```

Then copy the new webhook signing secret from Stripe and update `STRIPE_WEBHOOK_SECRET` in both `order-service` and `celery-worker`/`celery-beat`.

---

## Verification Checklist

Run these in order after all services are deployed:

```bash
# 1. Gateway health (verifies Kong is up)
curl https://<gateway-url>/health/identity
# Expected: {"status": "healthy", "services": {"postgres": "healthy", "redis": "healthy"}}

# 2. Django health (verifies Django + DB + Redis)
curl https://<gateway-url>/health/django
# Expected: {"status": "healthy", "services": {"postgres": "healthy", "redis": "healthy"}}

# 3. Public product list (verifies Django routing through Kong)
curl https://<gateway-url>/api/products/items/
# Expected: 200 with product list (or empty list if no products seeded)

# 4. Register a user (verifies FastAPI + DB through Kong)
curl -X POST https://<gateway-url>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "StrongerP@ss123"}'
# Expected: 201 with user object

# 5. Copy verify URL from identity-service Railway logs
# 6. Call verify-email endpoint
curl https://<gateway-url>/api/auth/verify-email/<token>

# 7. Login
curl -X POST https://<gateway-url>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "StrongerP@ss123"}'
# Expected: access_token + refresh_token

# 8. Protected order (verifies Kong JWT enforcement)
curl -X POST https://<gateway-url>/api/orders/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"items": [{"product": 1, "quantity": 1}]}'
```

---

## Summary of Files to Change

| # | File | Action |
|---|---|---|
| 1 | `Identity Service/main.py` | MODIFY — make ORDER_SERVICE_SYNC_URL configurable |
| 2 | `Identity Service/railway.toml` | VERIFY — already correct |
| 3 | `Order & Catalog Service/railway.toml` | MODIFY — add migrate + collectstatic to start cmd |
| 4 | `Order & Catalog Service/config/settings/production.py` | MODIFY — DATABASE_URL parsing + SSL fix |
| 5 | `Order & Catalog Service/config/settings/base.py` | MODIFY — fix REDIS_URL defaults |
| 6 | `Order & Catalog Service/requirements.txt` | MODIFY — add gunicorn + dj-database-url |
| 7 | `Order & Catalog Service/config/env_validator.py` | MODIFY — remove POSTGRES_* from required vars |
| 8 | `gateway/Dockerfile` | NEW — Kong as deployable Docker service |
| 9 | `gateway/docker-entrypoint.sh` | NEW — template rendering at startup |
| 10 | `gateway/kong.template.yml` | MODIFY — update upstream URLs to Railway internal |
| 11 | `gateway/railway.toml` | NEW — Kong gateway service config |
