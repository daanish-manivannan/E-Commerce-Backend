# Create your views here.
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .models import CustomUser
from .serializers import UserRegistrationSerializer


class RegisterView(generics.CreateAPIView):
    queryset = CustomUser.objects.all()
    permission_classes = (
        AllowAny,
    )  # Anyone can access this, even if they aren't logged in
    serializer_class = UserRegistrationSerializer
