from rest_framework import serializers
from .models import Category, Product

# 1. DEFINE THIS FIRST
class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'category', 'category_name', 'name', 
            'description', 'price', 'stock', 'is_active'
        ]

# 2. DEFINE THIS SECOND (Now it can safely reference ProductSerializer!)
class CategorySerializer(serializers.ModelSerializer):
    products = ProductSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ['id', 'name', 'description', 'is_active', 'products']