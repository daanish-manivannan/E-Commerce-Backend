"""
Production settings for the config project.

These settings are used for production deployment.
Security and performance optimizations are enabled here.
"""

import os as _os

import dj_database_url
from config.env_validator import validate_required_env_vars

# Validate environment on startup for production
from decouple import config

from .base import *  # noqa: F401, F403

validate_required_env_vars()

# Production-specific settings
DEBUG = False

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1").split(",")

# Railway injects RAILWAY_PUBLIC_DOMAIN automatically on deployment
_railway_domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
if _railway_domain:
    ALLOWED_HOSTS.append(_railway_domain)
    CSRF_TRUSTED_ORIGINS = [f"https://{_railway_domain}"]

# Database — Railway injects DATABASE_URL automatically via its Postgres plugin.
# Fall back to individual POSTGRES_* vars for non-Railway environments.
_db_url = _os.environ.get("DATABASE_URL")
if _db_url:
    DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("POSTGRES_DB"),
            "USER": config("POSTGRES_USER"),
            "PASSWORD": config("POSTGRES_PASSWORD"),
            "HOST": config("POSTGRES_HOST", default="db"),
            "PORT": config("POSTGRES_PORT", default="5432"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {
                "connect_timeout": 10,
            },
        }
    }

# SSL — Railway terminates TLS at its load balancer; Django receives plain HTTP
# internally. Setting SECURE_SSL_REDIRECT = True causes an infinite redirect
# loop on Railway. We instead trust Railway's X-Forwarded-Proto header so that
# session and CSRF cookies still use the Secure flag.
SECURE_SSL_REDIRECT = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Additional security
SECURE_CONTENT_TYPE_NOSNIFF = True

# Production logging

# Restrict CORS for production
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS", default="http://localhost:3000"
).split(",")
