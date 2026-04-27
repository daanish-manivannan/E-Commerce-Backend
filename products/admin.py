from django.contrib import admin
from .models import Product, Category

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_at')
    search_fields = ('name',)

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # Added category and stock to the main display table
    list_display = ('name', 'category', 'price', 'stock', 'is_active')
    
    # This creates a handy filtering sidebar in the admin panel!
    list_filter = ('category', 'is_active') 
    
    search_fields = ('name', 'description')