from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

class CategoryViewSet(viewsets.ModelViewSet):
    # Only show active categories
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    
    # Anyone can view, but only logged-in users can create/edit
    permission_classes = [IsAuthenticatedOrReadOnly] 

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]