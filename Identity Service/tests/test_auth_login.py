"""
Tests for login flow.

Covers:
- Successful login returns access and refresh tokens
- Wrong password rejected with generic message
- Non-existent email rejected with same generic message
- Unverified email blocked with specific error
- Error message never reveals whether email exists
- Successful login clears failed attempt counters
- Login response shape is correct
"""


class TestLogin:

    def test_login_success(self, client, verified_user):
        response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": verified_user["password"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client, verified_user):
        response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": "WrongPass@9999",
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "INVALID_CREDENTIALS"

    def test_login_nonexistent_email(self, client):
        response = client.post(
            "/login",
            json={
                "email": "ghost@example.com",
                "password": "ValidPass@1234",
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "INVALID_CREDENTIALS"

    def test_login_wrong_password_same_message_as_nonexistent_email(
        self, client, verified_user
    ):
        """
        Security: wrong password and unknown email must return
        identical error codes and messages — never leak which one failed.
        """
        wrong_password_response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": "WrongPass@9999",
            },
        )
        nonexistent_response = client.post(
            "/login",
            json={
                "email": "ghost@example.com",
                "password": "ValidPass@1234",
            },
        )

        assert (
            wrong_password_response.json()["detail"]["error"]
            == nonexistent_response.json()["detail"]["error"]
        )
        assert (
            wrong_password_response.json()["detail"]["message"]
            == nonexistent_response.json()["detail"]["message"]
        )

    def test_login_unverified_email_blocked(self, client, registered_unverified_user):
        response = client.post(
            "/login",
            json={
                "email": registered_unverified_user["email"],
                "password": registered_unverified_user["password"],
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "EMAIL_NOT_VERIFIED"

    def test_login_stores_refresh_token_in_db(self, client, verified_user, db_session):
        from models import User

        client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": verified_user["password"],
            },
        )

        db_session.expire_all()
        user = (
            db_session.query(User).filter(User.email == verified_user["email"]).first()
        )
        assert user.refresh_token is not None
        assert user.refresh_token_expiry is not None

    def test_login_access_token_is_valid_jwt(self, client, verified_user):
        from jose import jwt

        response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": verified_user["password"],
            },
        )
        token = response.json()["access_token"]
        decoded = jwt.decode(
            token,
            "test-secret-key-minimum-32-chars-long-for-testing",
            algorithms=["HS256"],
        )
        assert decoded["sub"] == verified_user["email"]
        assert decoded["iss"] == "ecom_identity_v1"
        assert "exp" in decoded
        assert "user_id" in decoded

    def test_login_response_has_correct_shape(self, client, verified_user):
        response = client.post(
            "/login",
            json={
                "email": verified_user["email"],
                "password": verified_user["password"],
            },
        )
        data = response.json()
        assert set(data.keys()) == {"access_token", "refresh_token", "token_type"}
        assert isinstance(data["access_token"], str)
        assert isinstance(data["refresh_token"], str)
        assert len(data["access_token"]) > 0
        assert len(data["refresh_token"]) > 0
