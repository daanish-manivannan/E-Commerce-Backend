import secrets
from datetime import datetime, timedelta

import httpx
import redis
from decouple import config  # 🔐 Swapped os.getenv for decouple
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

import auth_utils

# Import your local modules
import models
import schemas
from database import engine, get_db

# Create the database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Identity Service")

# Initialize Redis client (falls back to localhost for local development)
redis_client = redis.from_url(
    config("REDIS_URL", default="redis://localhost:6379/0"), decode_responses=True
)


# MUST include /orders/ in the path now
ORDER_SERVICE_SYNC_URL = "http://order-service:8000/api/orders/users/sync/"


@app.get("/")
async def read_root():
    return {"message": "Identity Service is online"}


@app.get("/db-test")
def test_db_connection(db: Session = Depends(get_db)):
    return {"status": "connected", "database": "ecom_db"}


@app.post(
    "/register",
    response_model=schemas.UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Registers a user locally, generates an email verification token,
    and syncs an inactive 'Shadow User' to the Order Service.
    """
    # 1. Check if user already exists in FastAPI DB
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # 2. Hash password and save to local Identity DB as inactive
    hashed_pwd = auth_utils.hash_password(user_data.password)
    verification_token = secrets.token_urlsafe(32)
    new_user = models.User(
        email=user_data.email,
        hashed_password=hashed_pwd,
        is_active=False,
        email_verified=False,
        email_verification_token=verification_token,
        email_verification_expiry=datetime.utcnow() + timedelta(hours=24),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. Log simulated verification email URL
    verification_url = (
        f"http://localhost:8080/api/auth/verify-email/{verification_token}"
    )
    print(f"\n📨 [Simulated Email] Verification link for {user_data.email}:")
    print(f"👉 {verification_url}\n")

    # 4. --- SHADOW USER SYNC (Service-to-Service) ---
    async with httpx.AsyncClient() as client:
        try:
            # 🔐 Safely load the secret using python-decouple
            cluster_secret = config(
                "INTERNAL_CLUSTER_SECRET", default="fallback_dev_only_key"
            )

            # We send the request to Django's internal sync endpoint with
            # is_active = False

            sync_response = await client.post(
                ORDER_SERVICE_SYNC_URL,
                json={"email": user_data.email, "is_active": False},
                headers={"X-Internal-Secret": cluster_secret},
                timeout=5.0,
            )

            # Log failure if sync isn't successful (don't block the user)
            if sync_response.status_code not in [200, 201]:
                print(
                    "⚠️ Shadow User sync failed. " f"Status: {sync_response.status_code}"
                )
                print(f"Details: {sync_response.text}")

        except Exception as e:
            print(f"❌ Connection to Order Service failed: {e}")

    return new_user


@app.post("/login", response_model=schemas.TokenResponse)
def login(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Authenticates user and returns a JWT access token and a refresh token.
    Ensures email has been verified.
    """
    # 1. Find the user
    user = db.query(models.User).filter(models.User.email == user_data.email).first()

    # 2. Verify existence and password
    if not user or not auth_utils.verify_password(
        user_data.password, user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # 3. Enforce email verification check
    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email address not verified. Please verify your email first.",
        )

    # 4. Create the tokens
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    refresh_token = auth_utils.create_refresh_token()

    # 5. Save refresh token to user record in DB
    user.refresh_token = refresh_token
    user.refresh_token_expiry = datetime.utcnow() + timedelta(days=7)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@app.post("/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    """
    Rotates the refresh token and returns a new access + refresh token pair.
    """
    # 1. Check if the token is blacklisted in Redis
    is_blacklisted = redis_client.get(f"blacklist:token:{payload.refresh_token}")
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is blacklisted",
        )

    # 2. Find the user with this refresh token
    user = (
        db.query(models.User)
        .filter(models.User.refresh_token == payload.refresh_token)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    # 3. Check expiration
    if not user.refresh_token_expiry or user.refresh_token_expiry < datetime.utcnow():
        # Clear expired token
        user.refresh_token = None
        user.refresh_token_expiry = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    # 4. Rotate tokens: generate new access and refresh tokens
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    new_refresh_token = auth_utils.create_refresh_token()

    # 5. Blacklist old refresh token in Redis (with TTL equal to
    # remaining expiry time, minimum 1 second)
    remaining_ttl = 0
    if user.refresh_token_expiry:
        remaining_ttl = int(
            (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
        )
    if remaining_ttl > 0:
        redis_client.setex(
            f"blacklist:token:{payload.refresh_token}", remaining_ttl, "revoked"
        )

    # 6. Save new refresh token details to db
    user.refresh_token = new_refresh_token
    user.refresh_token_expiry = datetime.utcnow() + timedelta(days=7)
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
    }


@app.post("/logout")
def logout(payload: schemas.TokenRefreshRequest, db: Session = Depends(get_db)):
    """
    Logs out the user and blacklists the refresh token.
    """
    # Find user by this refresh token
    user = (
        db.query(models.User)
        .filter(models.User.refresh_token == payload.refresh_token)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid refresh token",
        )

    # Add to Redis blacklist (with TTL equal to remaining expiry time, minimum 1 second)
    remaining_ttl = 0
    if user.refresh_token_expiry:
        remaining_ttl = int(
            (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
        )
    if remaining_ttl > 0:
        redis_client.setex(
            f"blacklist:token:{payload.refresh_token}",
            remaining_ttl,
            "logged_out",
        )

    # Clear from DB
    user.refresh_token = None
    user.refresh_token_expiry = None
    db.commit()

    return {"message": "Successfully logged out"}


@app.get("/verify-email/{token}")
async def verify_email(token: str, db: Session = Depends(get_db)):
    """
    Verifies the user's email address and activates their account.
    """
    # 1. Find user by verification token
    user = (
        db.query(models.User)
        .filter(models.User.email_verification_token == token)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification token",
        )

    # 2. Check token expiry
    if (
        user.email_verification_expiry
        and user.email_verification_expiry < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification token has expired. Please register again.",
        )

    # 3. Mark user as verified and active
    user.email_verified = True
    user.is_active = True
    user.email_verification_token = None
    user.email_verification_expiry = None
    db.commit()

    # 4. Sync status to Django (is_active = True)
    async with httpx.AsyncClient() as client:
        try:
            cluster_secret = config(
                "INTERNAL_CLUSTER_SECRET", default="fallback_dev_only_key"
            )
            sync_response = await client.post(
                ORDER_SERVICE_SYNC_URL,
                json={"email": user.email, "is_active": True},
                headers={"X-Internal-Secret": cluster_secret},
                timeout=5.0,
            )
            if sync_response.status_code not in [200, 201]:
                print(
                    "⚠️ Shadow User sync failed on verification status. "
                    f"Status: {sync_response.status_code}"
                )
        except Exception as e:
            print(f"❌ Connection to Order Service failed on verification: {e}")

    return {"message": "Email verified successfully! Your account is now active."}


@app.post("/forgot-password")
def forgot_password(
    payload: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)
):
    """
    Generates a secure password reset token and prints the simulated reset link.
    """
    # 1. Look up user by email
    user = db.query(models.User).filter(models.User.email == payload.email).first()

    # 2. Return HTTP 200 generic message if not found to prevent user enumeration
    if not user:
        return {
            "message": (
                "If the email is registered, a password reset link has been sent."
            )
        }

    # 3. Generate token and expiry
    reset_token = secrets.token_urlsafe(32)
    user.password_reset_token = reset_token
    user.password_reset_expiry = datetime.utcnow() + timedelta(hours=1)
    db.commit()

    # 4. Log simulated reset email
    reset_url = f"http://localhost:8080/api/auth/reset-password?token={reset_token}"
    print(f"\n📨 [Simulated Email] Password reset link for {payload.email}:")
    print(f"👉 {reset_url}\n")

    return {
        "message": "If the email is registered, a password reset link has been sent."
    }


@app.post("/reset-password")
def reset_password(
    payload: schemas.PasswordResetConfirm, db: Session = Depends(get_db)
):
    """
    Resets the user password, invalidating any active session.
    """
    # 1. Find user by reset token
    user = (
        db.query(models.User)
        .filter(models.User.password_reset_token == payload.token)
        .first()
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # 2. Check token expiry
    if user.password_reset_expiry and user.password_reset_expiry < datetime.utcnow():
        user.password_reset_token = None
        user.password_reset_expiry = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )

    # 3. Update password
    hashed_pwd = auth_utils.hash_password(payload.new_password)
    user.hashed_password = hashed_pwd

    # 4. Invalidate/revoke current refresh token to force re-login on all devices
    if user.refresh_token:
        # Blacklist it in Redis
        remaining_ttl = 0
        if user.refresh_token_expiry:
            remaining_ttl = int(
                (user.refresh_token_expiry - datetime.utcnow()).total_seconds()
            )
        if remaining_ttl > 0:
            redis_client.setex(
                f"blacklist:token:{user.refresh_token}",
                remaining_ttl,
                "revoked",
            )
        user.refresh_token = None
        user.refresh_token_expiry = None

    # Clear reset token and expiry
    user.password_reset_token = None
    user.password_reset_expiry = None
    db.commit()

    return {
        "message": (
            "Password reset successfully! Please log in with your new password."
        )
    }
