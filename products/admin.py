from django.contrib import admin

# Register your models here.
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # This dictates which columns show up in the admin table
    list_display = ('name', 'price', 'is_active', 'created_at')
    
    # This adds a search bar for the name and description
    search_fields = ('name', 'description')