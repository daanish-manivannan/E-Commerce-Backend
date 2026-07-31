import os
import uuid

import httpx
import pytest

# Determine the base URL for the API Gateway
# If running locally without docker-compose for the test runner, it hits localhost:8080
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")


@pytest.fixture(scope="session")
def test_user_email():
    # Use a unique email for each test run to avoid conflicts
    return f"testuser_{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(scope="session")
def test_user_password():
    return "SecurePassword123!"


@pytest.mark.asyncio
async def test_e2e_flow(test_user_email, test_user_password):
    """
    Test the full E2E flow:
    1. Register user
    2. Login (should fail because email not verified)
    3. Check public products route
    4. Check protected orders route
    """
    async with httpx.AsyncClient(base_url=GATEWAY_URL) as client:
        # 1. Register User
        res = await client.post(
            "/api/auth/register",
            json={"email": test_user_email, "password": test_user_password},
        )
        assert res.status_code == 201, f"Registration failed: {res.text}"

        # 2. Login (Expect 403 Forbidden because email is not verified)
        res = await client.post(
            "/api/auth/login",
            json={"email": test_user_email, "password": test_user_password},
        )
        assert (
            res.status_code == 403
        ), f"Expected 403 (unverified email), got {res.status_code}"
        assert "EMAIL_NOT_VERIFIED" in res.text

        # 3. Check public products route (should work without auth)
        res = await client.get("/api/products/items/")
        assert res.status_code == 200, f"Products route failed: {res.text}"

        # 4. Check protected orders route (should fail without auth)
        res = await client.get("/api/orders/")
        assert (
            res.status_code == 401
        ), f"Expected 401 for protected orders route, got {res.status_code}"
