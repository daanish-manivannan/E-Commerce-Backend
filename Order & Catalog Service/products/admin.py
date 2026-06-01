from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price", "stock", "is_active", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "description")
    list_editable = (
        "price",
        "stock",
        "is_active",
    )  # Allows quick updates from the main table list view
