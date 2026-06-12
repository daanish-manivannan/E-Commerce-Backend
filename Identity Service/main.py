import asyncio
import logging
import secrets
import sys
from datetime import datetime, timedelta

import auth_utils
import httpx

# Import your local modules
import models
import redis
import schemas
from database import engine, get_db
from decouple import config  # 🔐 Swapped os.getenv for decouple
from fastapi import Depends, FastAPI, HTTPException, Request, status
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pythonjsonlogger import jsonlogger
from sqlalchemy.orm import Session
from starlette.responses import Response

# Create the database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Identity Service")


@app.middleware("http")
async def track_requests(request: Request, call_next):
    import time

    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    return response


# Initialize Redis client (falls back to localhost for local development)
redis_client = redis.from_url(
    config("REDIS_URL", default="redis://localhost:6379/0"), decode_responses=True
)


# MUST include /orders/ in the path now
ORDER_SERVICE_SYNC_URL = "http://order-service:8000/api/orders/users/sync/"


# --- STRUCTURED JSON LOGGING SETUP ---
def setup_logging() -> None:
    """
    Configure root logger to emit JSON lines to stdout.
    Every log record will include: timestamp, level, message,
    logger name, and any extra fields passed at call time.
    """
    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


setup_logging()

logger = logging.getLogger("identity_service")
audit_logger = logging.getLogger("identity_service.audit")

# --- PROMETHEUS METRICS ---
REQUEST_COUNT = Counter(
    "identity_requests_total",
    "Total number of requests to the identity service",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "identity_request_duration_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)

AUTH_LOGIN_COUNTER = Counter(
    "identity_auth_logins_total",
    "Total login attempts",
    ["result"],  # success or failure
)


def error_response(code: str, message: str, status_code: int) -> HTTPException:
    """
    Returns a standardised HTTPException with a consistent error body.
    Use this everywhere instead of raising HTTPException directly.

    Shape: {"error": "ERROR_CODE", "message": "...", "timestamp": "..."}
    """
    return HTTPException(
        status_code=status_code,
        detail={
            "error": code,
            "message": message,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


# --- FAILED AUTH TRACKING CONFIGURATION ---
# Email lockout: 5 failures on one email → locked for 15 min
# IP lockout: 20 failures from one IP → locked for 15 min
# Progressive delay: kicks in at attempt 3, adds 2s pause before responding
#
# Redis key schema:
#   auth:failed:email:<email>  → attempt count
#   auth:lockout:email:<email> → "locked"
#   auth:failed:ip:<ip>        → attempt count
#   auth:lockout:ip:<ip>       → "locked"

MAX_ATTEMPTS_EMAIL = 5
MAX_ATTEMPTS_IP = 20
WARN_THRESHOLD = 3
LOCKOUT_SECONDS = 900  # 15 minutes
PROGRESSIVE_DELAY_SECONDS = 2


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_lockout(identifier: str, kind: str) -> None:
    lockout_key = f"auth:lockout:{kind}:{identifier}"
    if redis_client.get(lockout_key):
        ttl = redis_client.ttl(lockout_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "TOO_MANY_ATTEMPTS",
                "message": f"Too many failed attempts. Try again in {max(ttl, 1)} seconds.",
                "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
            headers={"Retry-After": str(max(ttl, 1))},
        )


def _record_failed_attempt(identifier: str, kind: str) -> int:
    counter_key = f"auth:failed:{kind}:{identifier}"
    lockout_key = f"auth:lockout:{kind}:{identifier}"
    max_attempts = MAX_ATTEMPTS_EMAIL if kind == "email" else MAX_ATTEMPTS_IP

    current = redis_client.incr(counter_key)
    if current == 1:
        redis_client.expire(counter_key, LOCKOUT_SECONDS)

    if current >= max_attempts:
        redis_client.setex(lockout_key, LOCKOUT_SECONDS, "locked")
        redis_client.delete(counter_key)

    return current


def _clear_failed_attempts(identifier: str, kind: str) -> None:
    redis_client.delete(f"auth:failed:{kind}:{identifier}")
    redis_client.delete(f"auth:lockout:{kind}:{identifier}")


@app.get("/")
async def read_root():
    return {"message": "Identity Service is online"}


@app.get("/health/identity")
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint. Verifies DB and Redis connectivity.
    Returns 200 if all dependencies are healthy, 503 if any are down.
    """
    from fastapi.responses import JSONResponse

    health = {"status": "healthy", "services": {}}
    status_code = 200

    # Check PostgreSQL
    try:
        db.execute(__import__("sqlalchemy").text("SELECT 1"))
        health["services"]["postgres"] = "healthy"
    except Exception as e:
        health["services"]["postgres"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    # Check Redis
    try:
        redis_client.ping()
        health["services"]["redis"] = "healthy"
    except Exception as e:
        health["services"]["redis"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    return JSONResponse(content=health, status_code=status_code)


@app.get("/metrics/identity")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


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
        raise error_response(
            "EMAIL_TAKEN", "Email already registered", status.HTTP_400_BAD_REQUEST
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
    logger.info(
        "Verification email simulated",
        extra={"email": user_data.email, "verification_url": verification_url},
    )

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
            logger.warning(
                "Shadow user sync failed",
                extra={
                    "status_code": sync_response.status_code,
                    "detail": sync_response.text,
                },
            )

        except Exception as e:
            logger.error("Connection to Order Service failed", extra={"error": str(e)})

    return new_user


@app.post("/login", response_model=schemas.TokenResponse)
async def login(
    user_data: schemas.UserCreate, request: Request, db: Session = Depends(get_db)
):
    """
    Authenticates user and returns a JWT access token and refresh token.
    Applies IP + email lockout and progressive delay on repeated failures.
    """
    client_ip = _get_client_ip(request)

    # 1. Pre-check lockouts before touching the DB
    _check_lockout(client_ip, "ip")
    _check_lockout(user_data.email, "email")

    # 2. Credential check
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    credential_valid = user is not None and auth_utils.verify_password(
        user_data.password, user.hashed_password
    )

    if not credential_valid:
        email_attempts = _record_failed_attempt(user_data.email, "email")
        _record_failed_attempt(client_ip, "ip")
        audit_logger.warning(
            "AUTH_LOGIN_FAILED",
            extra={
                "email": user_data.email,
                "ip": client_ip,
                "attempt": email_attempts,
            },
        )
        AUTH_LOGIN_COUNTER.labels(result="failure").inc()

        # Progressive delay before responding — slows brute force without full lockout yet
        if WARN_THRESHOLD <= email_attempts < MAX_ATTEMPTS_EMAIL:
            await asyncio.sleep(PROGRESSIVE_DELAY_SECONDS)

        # Re-check in case this attempt just triggered lockout
        _check_lockout(user_data.email, "email")
        _check_lockout(client_ip, "ip")

        # Generic message — never reveal whether the email exists
        raise error_response(
            "INVALID_CREDENTIALS",
            "Incorrect email or password",
            status.HTTP_401_UNAUTHORIZED,
        )

    # 3. Email verification gate
    if not user.email_verified:
        raise error_response(
            "EMAIL_NOT_VERIFIED",
            "Email address not verified. Please verify your email first.",
            status.HTTP_403_FORBIDDEN,
        )

    # 4. Success — clear all failed attempt state
    _clear_failed_attempts(user_data.email, "email")
    _clear_failed_attempts(client_ip, "ip")

    audit_logger.info(
        "AUTH_LOGIN_SUCCESS",
        extra={"email": user_data.email, "ip": client_ip},
    )
    AUTH_LOGIN_COUNTER.labels(result="success").inc()

    # 5. Issue tokens
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    refresh_token = auth_utils.create_refresh_token()

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
        raise error_response(
            "TOKEN_BLACKLISTED",
            "Refresh token is blacklisted",
            status.HTTP_401_UNAUTHORIZED,
        )

    # 2. Find the user with this refresh token
    user = (
        db.query(models.User)
        .filter(models.User.refresh_token == payload.refresh_token)
        .first()
    )
    if not user:
        raise error_response(
            "INVALID_TOKEN", "Invalid refresh token", status.HTTP_401_UNAUTHORIZED
        )

    # 3. Check expiration
    if not user.refresh_token_expiry or user.refresh_token_expiry < datetime.utcnow():
        # Clear expired token
        user.refresh_token = None
        user.refresh_token_expiry = None
        db.commit()
        raise error_response(
            "TOKEN_EXPIRED", "Refresh token has expired", status.HTTP_401_UNAUTHORIZED
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
        raise error_response(
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
    audit_logger.info(
        "AUTH_LOGOUT",
        extra={"user_refresh_token_prefix": payload.refresh_token[:8]},
    )

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
        raise error_response(
            "INVALID_TOKEN", "Invalid verification token", status.HTTP_400_BAD_REQUEST
        )

    # 2. Check token expiry
    if (
        user.email_verification_expiry
        and user.email_verification_expiry < datetime.utcnow()
    ):
        raise error_response(
            "TOKEN_EXPIRED",
            "Verification token has expired. Please register again.",
            status.HTTP_400_BAD_REQUEST,
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
                logger.warning(
                    "Shadow user sync failed on verification",
                    extra={"status_code": sync_response.status_code},
                )
        except Exception as e:
            logger.error(
                "Connection to Order Service failed on verification",
                extra={"error": str(e)},
            )
    audit_logger.info(
        "AUTH_EMAIL_VERIFIED",
        extra={"email": user.email},
    )
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
    logger.info(
        "Password reset email simulated",
        extra={"email": payload.email, "reset_url": reset_url},
    )

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
        raise error_response(
            "INVALID_TOKEN",
            "Invalid or expired reset token",
            status.HTTP_400_BAD_REQUEST,
        )

    # 2. Check token expiry
    if user.password_reset_expiry and user.password_reset_expiry < datetime.utcnow():
        user.password_reset_token = None
        user.password_reset_expiry = None
        db.commit()
        raise error_response(
            "TOKEN_EXPIRED", "Reset token has expired", status.HTTP_400_BAD_REQUEST
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

    audit_logger.info(
        "AUTH_PASSWORD_RESET",
        extra={"token_prefix": payload.token[:8]},
    )
    return {
        "message": (
            "Password reset successfully! Please log in with your new password."
        )
    }
