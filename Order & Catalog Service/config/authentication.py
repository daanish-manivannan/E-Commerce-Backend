import jwt
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

# Reference the active CustomUser model configured in your settings
User = get_user_model()


class KongJWTAuthentication(authentication.BaseAuthentication):
    """
    Authenticate using JWT token from Authorization header.
    Supports both:
    1. X-User-Email/X-User-Id headers (from Kong request-transformer)
    2. Bearer token in Authorization header (verified by Kong, decoded by Django)
    """

    def authenticate(self, request):
        # Try 1: Read headers injected by Kong request-transformer
        email = request.META.get("HTTP_X_USER_EMAIL")
        user_id = request.META.get("HTTP_X_USER_ID")

        if email:
            # Kong already processed the JWT and added headers
            try:
                user, created = User.objects.get_or_create(
                    email=email, defaults={"id": user_id} if user_id else {}
                )
                return (user, None)
            except Exception as e:
                raise exceptions.AuthenticationFailed(f"Auth error: {str(e)}") from e

        # Try 2: Parse JWT from Authorization header
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header.startswith("Bearer "):
            return None  # No auth provided

        # 🛡️ GATEWAY VERIFICATION CHECK: Enforce that Kong validated this token.
        # Kong's JWT plugin sets X-Consumer-Username to the consumer's username
        # (identity-service) upon successful JWT verification.
        consumer_username = request.META.get("HTTP_X_CONSUMER_USERNAME")
        if not consumer_username or consumer_username != "identity-service":
            raise exceptions.AuthenticationFailed(
                "Access denied: Request must be authenticated by the Kong gateway."
            )

        try:
            # Extract token
            token = auth_header[7:]  # Remove 'Bearer ' prefix

            # Decode JWT without verification first to get claims
            # (We've already verified the signature via Kong's edge validation)
            decoded = jwt.decode(token, options={"verify_signature": False})

            email = decoded.get("sub")  # 'sub' claim contains email
            user_id = decoded.get("user_id")

            if not email:
                raise exceptions.AuthenticationFailed("No email in token")

            # Create or get user
            user, created = User.objects.get_or_create(
                email=email, defaults={"id": user_id} if user_id else {}
            )

            return (user, None)

        except jwt.DecodeError as e:
            raise exceptions.AuthenticationFailed("Invalid token format") from e
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Auth error: {str(e)}") from e
