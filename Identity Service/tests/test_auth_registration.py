"""
Tests for user registration and email verification flows.

Covers:
- Successful registration
- Duplicate email rejection
- Weak password rejection
- Email verification with valid token
- Email verification with invalid token
- Email verification with expired token
- Login blocked before email verification
"""

from datetime import datetime, timedelta


class TestRegistration:

    def test_register_success(self, client):
        response = client.post(
            "/register",
            json={"email": "newuser@example.com", "password": "ValidPass@1234"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is False
        assert "hashed_password" not in data

    def test_register_duplicate_email(self, client):
        payload = {"email": "dupe@example.com", "password": "ValidPass@1234"}
        client.post("/register", json=payload)
        response = client.post("/register", json=payload)
        assert response.status_code == 400
        # assert response.json()["error"] == "EMAIL_TAKEN"
        assert response.json()["detail"]["error"] == "EMAIL_TAKEN"

    def test_register_password_too_short(self, client):
        response = client.post(
            "/register",
            json={"email": "short@example.com", "password": "Short@1"},
        )
        assert response.status_code == 422

    def test_register_password_no_uppercase(self, client):
        response = client.post(
            "/register",
            json={"email": "noupper@example.com", "password": "nouppercase@1234"},
        )
        assert response.status_code == 422

    def test_register_password_no_special_char(self, client):
        response = client.post(
            "/register",
            json={"email": "nospecial@example.com", "password": "NoSpecialChar1234"},
        )
        assert response.status_code == 422

    def test_register_invalid_email(self, client):
        response = client.post(
            "/register",
            json={"email": "not-an-email", "password": "ValidPass@1234"},
        )
        assert response.status_code == 422

    def test_registered_user_stored_inactive(self, client, db_session):
        from models import User

        client.post(
            "/register",
            json={"email": "inactive@example.com", "password": "ValidPass@1234"},
        )
        user = (
            db_session.query(User).filter(User.email == "inactive@example.com").first()
        )
        assert user is not None
        assert user.is_active is False
        assert user.email_verified is False
        assert user.email_verification_token is not None


class TestEmailVerification:

    def test_verify_email_success(self, client, registered_unverified_user, db_session):
        from models import User

        token = registered_unverified_user["verification_token"]
        response = client.get(f"/verify-email/{token}")

        assert response.status_code == 200
        assert "verified" in response.json()["message"].lower()

        db_session.expire_all()
        user = (
            db_session.query(User)
            .filter(User.email == registered_unverified_user["email"])
            .first()
        )
        assert user.email_verified is True
        assert user.is_active is True
        assert user.email_verification_token is None

    def test_verify_email_invalid_token(self, client):
        response = client.get("/verify-email/totally-invalid-token-abc123")
        assert response.status_code == 400
        # assert response.json()["error"] == "INVALID_TOKEN"
        assert response.json()["detail"]["error"] == "INVALID_TOKEN"

    def test_verify_email_expired_token(
        self, client, registered_unverified_user, db_session
    ):
        from models import User

        # Manually expire the token
        user = (
            db_session.query(User)
            .filter(User.email == registered_unverified_user["email"])
            .first()
        )
        user.email_verification_expiry = datetime.utcnow() - timedelta(hours=1)
        db_session.commit()

        token = registered_unverified_user["verification_token"]
        response = client.get(f"/verify-email/{token}")

        assert response.status_code == 400
        # assert response.json()["error"] == "TOKEN_EXPIRED"
        assert response.json()["detail"]["error"] == "TOKEN_EXPIRED"

    def test_login_blocked_before_verification(
        self, client, registered_unverified_user
    ):
        response = client.post(
            "/login",
            json={
                "email": registered_unverified_user["email"],
                "password": registered_unverified_user["password"],
            },
        )
        assert response.status_code == 403
        # assert response.json()["error"] == "EMAIL_NOT_VERIFIED"
        assert response.json()["detail"]["error"] == "EMAIL_NOT_VERIFIED"
