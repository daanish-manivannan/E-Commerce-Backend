import os
from rest_framework import authentication, exceptions
from jose import jwt, JWTError
from django.contrib.auth import get_user_model # Correct import

SECRET_KEY = os.getenv("JWT_SECRET", "fallback_do_not_use_in_prod") 
ALGORITHM = "HS256"

# THIS IS THE MISSING LINE:
# We ask Django for the active user model and name it 'User'
User = get_user_model()

class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return None

        try:
            token = auth_header.split(' ')[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            email = payload.get("sub")
            if not email:
                return None

            # Now 'User' is defined and points to your CustomUser
            # user, _ = User.objects.get_or_create(username=email, email=email)
            user, _ = User.objects.get_or_create(email=email)
            return (user, None)

        except (JWTError, IndexError):
            raise exceptions.AuthenticationFailed('Invalid or expired token')