"""
Tests for refresh token rotation and logout flows.

Covers:
- Refresh with valid token returns new token pair
- Refresh rotates the refresh token (old token no longer valid)
- Refresh with invalid token rejected
- Refresh with blacklisted token rejected
- Refresh with expired token rejected
- Logout blacklists the refresh token
- Logout clears refresh token from DB
- Cannot refresh after logout
- Cannot logout twice with same token
"""


class TestRefreshToken:

    def test_refresh_success(self, client, logged_in_user):
        response = client.post(
            "/refresh",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_refresh_returns_new_tokens(self, client, logged_in_user):
        """
        Refresh token must always be rotated to a new value.
        Access token may be identical if generated within the same second
        (same exp claim), so we only assert the refresh token changes.
        """
        response = client.post(
            "/refresh",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )
        data = response.json()
        assert data["refresh_token"] != logged_in_user["refresh_token"]

    def test_refresh_old_token_rejected_after_rotation(self, client, logged_in_user):
        """
        After rotation, the old refresh token must be blacklisted.
        Using it again must be rejected.
        """
        old_refresh_token = logged_in_user["refresh_token"]

        # First refresh — rotates the token
        client.post(
            "/refresh",
            json={"refresh_token": old_refresh_token},
        )

        # Second refresh with old token — must be rejected
        response = client.post(
            "/refresh",
            json={"refresh_token": old_refresh_token},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "TOKEN_BLACKLISTED"

    def test_refresh_invalid_token_rejected(self, client):
        response = client.post(
            "/refresh",
            json={"refresh_token": "completely-invalid-token-xyz"},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "INVALID_TOKEN"

    def test_refresh_expired_token_rejected(self, client, logged_in_user, db_session):
        from datetime import datetime, timedelta

        from models import User

        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        user.refresh_token_expiry = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        response = client.post(
            "/refresh",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "TOKEN_EXPIRED"

    def test_refresh_clears_expired_token_from_db(
        self, client, logged_in_user, db_session
    ):
        from datetime import datetime, timedelta

        from models import User

        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        user.refresh_token_expiry = datetime.utcnow() - timedelta(days=1)
        db_session.commit()

        client.post(
            "/refresh",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        assert user.refresh_token is None
        assert user.refresh_token_expiry is None

    def test_new_refresh_token_stored_in_db_after_rotation(
        self, client, logged_in_user, db_session
    ):
        from models import User

        response = client.post(
            "/refresh",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )
        new_refresh_token = response.json()["refresh_token"]

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        assert user.refresh_token == new_refresh_token


class TestLogout:

    def test_logout_success(self, client, logged_in_user):
        response = client.post(
            "/logout",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )
        assert response.status_code == 200
        assert "message" in response.json()

    def test_logout_clears_refresh_token_from_db(
        self, client, logged_in_user, db_session
    ):
        from models import User

        client.post(
            "/logout",
            json={"refresh_token": logged_in_user["refresh_token"]},
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == logged_in_user["email"]).first()
        )
        assert user.refresh_token is None
        assert user.refresh_token_expiry is None

    def test_cannot_refresh_after_logout(self, client, logged_in_user):
        refresh_token = logged_in_user["refresh_token"]

        client.post("/logout", json={"refresh_token": refresh_token})

        response = client.post(
            "/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] in (
            "TOKEN_BLACKLISTED",
            "INVALID_TOKEN",
        )

    def test_logout_invalid_token_rejected(self, client):
        response = client.post(
            "/logout",
            json={"refresh_token": "invalid-token-xyz"},
        )
        assert response.status_code == 400

    def test_cannot_logout_twice_with_same_token(self, client, logged_in_user):
        refresh_token = logged_in_user["refresh_token"]

        client.post("/logout", json={"refresh_token": refresh_token})

        response = client.post(
            "/logout",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 400
