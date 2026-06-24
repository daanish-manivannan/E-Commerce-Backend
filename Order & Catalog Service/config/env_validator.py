"""
Environment variable validation utilities.
Ensures all critical configuration is present before app startup.
"""

import os

from decouple import config


def validate_required_env_vars() -> None:
    """
    Validate that all required environment variables are set.

    Raises:
        ValueError: If any required environment variable is missing.
    """
    REQUIRED_VARS = {
        "SECRET_KEY": "Django internal secret key",
        "JWT_SECRET": "Shared JWT secret for auth services",
        # POSTGRES_* vars not required on Railway — DATABASE_URL is injected automatically
        # by the Railway Postgres plugin and parsed by dj-database-url in production.py.
        "STRIPE_PUBLIC_KEY": "Stripe publishable key",
        "STRIPE_SECRET_KEY": "Stripe secret key",
        "STRIPE_WEBHOOK_SECRET": "Stripe webhook secret",
    }

    missing_vars = []
    for var_name, description in REQUIRED_VARS.items():
        if not os.getenv(var_name):
            missing_vars.append(f"  - {var_name}: {description}")

    if missing_vars:
        error_msg = (
            "❌ Missing required environment variables:\n"
            + "\n".join(missing_vars)
            + "\n\nPlease add these to your .env file and try again."
        )
        raise ValueError(error_msg)


def validate_stripe_keys() -> None:
    """
    Validate Stripe configuration is valid format.
    """
    public_key = config("STRIPE_PUBLIC_KEY", default="")
    secret_key = config("STRIPE_SECRET_KEY", default="")

    if not public_key.startswith("pk_"):
        raise ValueError("Invalid STRIPE_PUBLIC_KEY format (should start with 'pk_')")

    if not secret_key.startswith("sk_"):
        raise ValueError("Invalid STRIPE_SECRET_KEY format (should start with 'sk_')")


if __name__ == "__main__":
    validate_required_env_vars()
    validate_stripe_keys()
    print("✅ All environment variables validated successfully!")
