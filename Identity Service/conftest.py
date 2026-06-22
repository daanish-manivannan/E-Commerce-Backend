import os

# Set environment variables BEFORE any app imports.
# auth_utils.py raises RuntimeError at import if JWT_SECRET is missing.
# database.py raises RuntimeError at import if DATABASE_URL is missing.
os.environ.setdefault("JWT_SECRET", "test-secret-key-minimum-32-chars-long-for-testing")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://ecom_user:ecom_password@localhost:5432/ecom_test_db",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("INTERNAL_CLUSTER_SECRET", "test-internal-secret")

import pytest
from database import Base, get_db
from fastapi.testclient import TestClient
from main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# --- TEST DATABASE ENGINE ---
# Points to ecom_test_db, not the real ecom_db.
TEST_DATABASE_URL = os.environ["DATABASE_URL"]
test_engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """
    Creates all tables in ecom_test_db at the start of the test session,
    and drops them all at the end. Runs once per pytest session.
    """
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_tables():
    """
    Truncates all tables between each test so tests don't bleed into each other.
    autouse=True means this runs automatically for every test without needing
    to be listed in the test function signature.
    """
    yield
    # Teardown: wipe all rows after each test
    with test_engine.connect() as conn:
        from sqlalchemy import text

        conn.execute(text("TRUNCATE TABLE identity_users RESTART IDENTITY CASCADE"))
        conn.commit()


@pytest.fixture()
def db_session():
    """
    Provides a real database session pointed at ecom_test_db.
    Used when tests need to directly query or insert DB rows.
    """
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    """
    FastAPI TestClient with the real database session overridden
    to use the test database instead of the production database.
    """

    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def registered_unverified_user(client, db_session):
    """
    Registers a user but does NOT verify their email.
    Returns the user's email, password, and verification token.
    """
    email = "testuser@example.com"
    password = "TestPass@1234"

    client.post("/register", json={"email": email, "password": password})

    from models import User

    user = db_session.query(User).filter(User.email == email).first()

    return {
        "email": email,
        "password": password,
        "verification_token": user.email_verification_token,
        "user": user,
    }


@pytest.fixture()
def verified_user(client, registered_unverified_user):
    """
    Registers and verifies a user. Ready for login.
    """
    token = registered_unverified_user["verification_token"]
    client.get(f"/verify-email/{token}")
    return registered_unverified_user


@pytest.fixture()
def logged_in_user(client, verified_user):
    """
    Registers, verifies, and logs in a user.
    Returns email, password, access_token, and refresh_token.
    """
    response = client.post(
        "/login",
        json={
            "email": verified_user["email"],
            "password": verified_user["password"],
        },
    )
    data = response.json()
    return {
        **verified_user,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }
