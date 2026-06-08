import os
import secrets
from datetime import datetime, timedelta

from jose import jwt
from passlib.context import CryptContext

# Setup bcrypt for password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT CONFIGURATION ---
# Hard fail at startup if JWT_SECRET is missing or still set to the placeholder.
# A missing secret means every token would be signed with a known public value —
# which makes the entire auth system trivially bypassable.
_raw_secret = os.getenv("JWT_SECRET", "")

if not _raw_secret or _raw_secret == "fallback_do_not_use_in_prod":
    raise RuntimeError(
        "JWT_SECRET is not set or is still the placeholder value. "
        'Generate one with: python -c "import secrets; print(secrets.token_hex(32))" '
        "and add it to your .env file."
    )

SECRET_KEY: str = _raw_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15


def create_access_token(data: dict) -> str:
    """
    Generates a secure JWT token signed with our shared cluster secret,
    optimized for Kong Gateway edge verification.
    """
    to_encode = data.copy()

    # 1. Enforce the standardized UTC expiration time window
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    # 🟢 THE FIX: Use a stable, clean string literal for the lookup key identifier
    to_encode.update({"iss": "ecom_identity_v1"})

    # Sign and encode using jose
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return str(encoded_jwt)


def create_refresh_token() -> str:
    """
    Generates a secure random refresh token.
    """
    return secrets.token_hex(32)
