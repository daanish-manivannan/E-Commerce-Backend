from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for viewing product categories.
    Bypasses auth so anyone can see classifications.
    """
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    permission_classes = [AllowAny] # 👈 CRITICAL: Allows public unauthenticated access

class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """
    A simple ViewSet for viewing active products.
    ReadOnlyModelViewSet explicitly disables POST/PUT/DELETE for clients.
    """
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [AllowAny] # 👈 CRITICAL: Allows public unauthenticated access