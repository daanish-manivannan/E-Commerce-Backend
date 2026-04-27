from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import Order
from .serializers import OrderSerializer

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    # You MUST be logged in with a JWT token to access this endpoint
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # SECURITY OVERRIDE: Users can only see orders they created!
        return Order.objects.filter(user=self.request.user).order_by('-created_at')