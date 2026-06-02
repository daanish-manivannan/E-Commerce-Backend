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
SECRET_KEY = os.getenv("JWT_SECRET", "fallback_do_not_use_in_prod")
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

    # # 2. 🚨 CRITICAL KONG HOOK: The 'iss' claim must match the
    # # Consumer key in kong.yml
    # to_encode.update({"iss": "ecom_identity"})

    # # 🔄 ALTERNATIVE HOOK: Force 'iss' to use actual SECRET_KEY value
    # to_encode.update({"iss": SECRET_KEY})

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
