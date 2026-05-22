import os
from rest_framework import authentication, exceptions
from jose import jwt, JWTError
from django.contrib.auth import get_user_model

# 1. Load the shared secret key directly from the container's environment variables
SECRET_KEY = os.getenv("JWT_SECRET", "fallback_do_not_use_in_prod") 
ALGORITHM = "HS256"

# 2. Reference the active CustomUser model configured in your settings
User = get_user_model()

class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        # 3. Extract the raw Authorization header string from request metadata
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header:
            return None

        try:
            # 4. Split 'Bearer <token>' safely to capture only the cryptographic string
            header_parts = auth_header.split(' ')
            if len(header_parts) != 2 or header_parts[0].lower() != 'bearer':
                return None
            
            token = header_parts[1]
            
            # 5. Decode and verify the signature using the shared secret and algorithm
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            
            # 6. Extract the unique email string from the token's 'sub' claim
            email = payload.get("sub")
            if not email:
                raise exceptions.AuthenticationFailed('Token payload is missing the identity claim ("sub")')

            # 7. Match against the synchronized shadow profile database record
            user, _ = User.objects.get_or_create(email=email)
            
            # Return the authenticated user instance to DRF to populate request.user
            return (user, None)

        # except (JWTError, IndexError):
        #     # Any signature verification failure, tampering, or expiration lands here
        #     raise exceptions.AuthenticationFailed('Invalid or expired token')
        
        except JWTError as e:
            # 🚨 This prints the EXACT cryptographic error to your terminal logs!
            print(f"--- JWT DECODE ERROR: {str(e)} ---")
            raise exceptions.AuthenticationFailed(f'JWT Decode Failed: {str(e)}')
            
        except Exception as e:
            # 🚨 This catches database, configuration, or structural coding faults!
            print(f"--- SYSTEM AUTHENTICATION ERROR: {str(e)} ---")
            raise exceptions.AuthenticationFailed(f'Internal Auth System Error: {str(e)}')