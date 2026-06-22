"""
Tests for forgot-password and reset-password flows.

Covers:
- forgot-password always returns 200 regardless of whether email exists
- forgot-password generates a reset token for existing users
- reset-password with valid token updates the password
- reset-password with invalid token rejected
- reset-password with expired token rejected
- reset-password invalidates existing refresh token
- New password must meet strength requirements
- Can login with new password after reset
- Cannot login with old password after reset
"""

from datetime import datetime, timedelta


class TestForgotPassword:

    def test_forgot_password_existing_email_returns_200(self, client, verified_user):
        response = client.post(
            "/forgot-password",
            json={"email": verified_user["email"]},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_forgot_password_nonexistent_email_also_returns_200(self, client):
        """
        Security: must not reveal whether an email is registered.
        Both existing and non-existing emails return identical 200 responses.
        """
        response = client.post(
            "/forgot-password",
            json={"email": "ghost@example.com"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_forgot_password_same_message_for_existing_and_nonexistent(
        self, client, verified_user
    ):
        existing_response = client.post(
            "/forgot-password",
            json={"email": verified_user["email"]},
        )
        nonexistent_response = client.post(
            "/forgot-password",
            json={"email": "ghost@example.com"},
        )
        assert (
            existing_response.json()["message"]
            == nonexistent_response.json()["message"]
        )

    def test_forgot_password_generates_token_for_existing_user(
        self, client, verified_user, db_session
    ):
        from models import User

        client.post(
            "/forgot-password",
            json={"email": verified_user["email"]},
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == verified_user["email"]).first()
        )
        assert user.password_reset_token is not None
        assert user.password_reset_expiry is not None
        assert user.password_reset_expiry > datetime.utcnow()

    def test_forgot_password_does_not_generate_token_for_nonexistent_user(
        self, client, db_session
    ):
        from models import User

        client.post(
            "/forgot-password",
            json={"email": "ghost@example.com"},
        )
        user = db_session.query(User).filter(User.email == "ghost@example.com").first()
        assert user is None


class TestResetPassword:

    def _get_reset_token(self, client, verified_user, db_session):
        """Helper: triggers forgot-password and returns the reset token from DB."""
        from models import User

        client.post(
            "/forgot-password",
            json={"email": verified_user["email"]},
        )
        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == verified_user["email"]).first()
        )
        return user.password_reset_token

    def test_reset_password_success(self, client, verified_user, db_session):
        token = self._get_reset_token(client, verified_user, db_session)
        response = client.post(
            "/reset-password",
            json={"token": token, "new_password": "NewValidPass@5678"},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_reset_password_invalid_token(self, client):
        response = client.post(
            "/reset-password",
            json={"token": "invalid-token-xyz", "new_password": "NewValidPass@5678"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "INVALID_TOKEN"

    def test_reset_password_expired_token(self, client, verified_user, db_session):
        from models import User

        token = self._get_reset_token(client, verified_user, db_session)

        user = (
            db_session.query(User).filter(User.email == verified_user["email"]).first()
        )
        user.password_reset_expiry = datetime.utcnow() - timedelta(hours=2)
        db_session.commit()

        response = client.post(
            "/reset-password",
            json={"token": token, "new_password": "NewValidPass@5678"},
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "TOKEN_EXPIRED"

    def test_reset_password_clears_token_from_db(
        self, client, verified_user, db_session
    ):
        from models import User

        token = self._get_reset_token(client, verified_user, db_session)
        client.post(
            "/reset-password",
            json={"token": token, "new_password": "NewValidPass@5678"},
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == verified_user["email"]).first()
        )
        assert user.password_reset_token is None
        assert user.password_reset_expiry is None

    def test_reset_password_invalidates_refresh_token(
        self, client, logged_in_user, db_session
    ):
        """
        After password reset, any active refresh token must be revoked
        to force re-login on all devices.
        """
        from models import User

        # Get reset token
        client.post(
            "/forgot-password",
            json={"email": logged_in_user["email"]},
        )
        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        reset_token = user.password_reset_token

        client.post(
            "/reset-password",
            json={"token": reset_token, "new_password": "NewValidPass@5678"},
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        assert user.refresh_token is None
        assert user.refresh_token_expiry is None

    def test_can_login_with_new_password_after_reset(
        self, client, verified_user, db_session
    ):
        token = self._get_reset_token(client, verified_user, db_session)
        new_password = "NewValidPass@5678"

        client.post(
            "/reset-password",
            json={"token": token, "new_password": new_password},
        )

        response = client.post(
            "/login",
            json={"email": verified_user["email"], "password": new_password},
        )
        assert response.status_code == 200
        assert "access_token" in response.json()

    def test_cannot_login_with_old_password_after_reset(
        self, client, verified_user, db_session
    ):
        token = self._get_reset_token(client, verified_user, db_session)

        client.post(
            "/reset-password",
            json={"token": token, "new_password": "NewValidPass@5678"},
        )

        response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": verified_user["password"],
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "INVALID_CREDENTIALS"

    def test_reset_password_weak_new_password_rejected(
        self, client, verified_user, db_session
    ):
        token = self._get_reset_token(client, verified_user, db_session)
        response = client.post(
            "/reset-password",
            json={"token": token, "new_password": "weak"},
        )
        assert response.status_code == 422
