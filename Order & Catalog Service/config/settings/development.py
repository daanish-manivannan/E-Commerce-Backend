"""
Development settings for the config project.

These settings are used for local development and testing.
"""

from decouple import config

from .base import *  # noqa: F401, F403

# Development-specific settings
DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "127.0.0.1:8000",
    "127.0.0.1:8080",
    "order-service",
    "gateway",
]


# Database configuration for development
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB", default="ecom_db"),
        "USER": config("POSTGRES_USER", default="ecom_user"),
        "PASSWORD": config("POSTGRES_PASSWORD", default="ecom_password"),
        "HOST": config("POSTGRES_HOST", default="localhost"),
        "PORT": config("POSTGRES_PORT", default="5432"),
    }
}

# Build mode support for collectstatic
IS_BUILD_MODE = config("DB_IGNORE", default=False, cast=bool)

# Environment validation happens at runtime via Django or service failures
# (removed strict validation - let config defaults handle development mode)

if IS_BUILD_MODE:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# Development logging

# Allow all origins for development (CORS)
CORS_ALLOW_ALL_ORIGINS = True

LOGGING["root"]["level"] = "DEBUG"  # type: ignore[index]  # noqa: F405
