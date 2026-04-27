from rest_framework import serializers
from .models import Category, Product

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductSerializer(serializers.ModelSerializer):
    # This automatically pulls the text name of the category, not just its ID!
    category_name = serializers.ReadOnlyField(source='category.name')

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'price', 'stock', 
            'category', 'category_name', 'is_active', 'created_at'
        ]