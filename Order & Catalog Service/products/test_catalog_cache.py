"""
Tests for product and category cache behavior.

Covers:
- First request populates cache (MISS then HIT)
- Cached response matches database response
- Product cache invalidated on product save
- Product cache invalidated on product delete
- Category cache invalidated on category save
- Category cache invalidated on category delete
- Cache keys are correct
- Detail endpoints bypass cache
"""

import pytest
from django.core.cache import cache
from django.urls import reverse
from products.models import Category, Product
from products.views import CATEGORY_LIST_CACHE_KEY, PRODUCT_LIST_CACHE_KEY
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after every test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def category(db):
    return Category.objects.create(name="Electronics", is_active=True)


@pytest.fixture
def product(category):
    from inventory.models import Inventory

    p = Product.objects.create(
        category=category,
        name="Wireless Mouse",
        price=50.00,
        is_active=True,
    )
    Inventory.objects.create(product=p, available_stock=10)
    return p


@pytest.fixture
def client():
    return APIClient()


@pytest.mark.django_db
class TestProductCache:

    def test_first_request_is_cache_miss(self, client, product):
        assert cache.get(PRODUCT_LIST_CACHE_KEY) is None
        client.get(reverse("products:product-list"))
        assert cache.get(PRODUCT_LIST_CACHE_KEY) is not None

    def test_second_request_is_cache_hit(self, client, product):
        client.get(reverse("products:product-list"))
        # Manually verify cache is populated
        cached = cache.get(PRODUCT_LIST_CACHE_KEY)
        assert cached is not None

        # Second request returns same data
        response = client.get(reverse("products:product-list"))
        assert response.status_code == 200

    def test_cached_response_matches_db(self, client, product):
        response1 = client.get(reverse("products:product-list"))
        response2 = client.get(reverse("products:product-list"))
        assert response1.json() == response2.json()

    def test_product_save_invalidates_cache(self, client, product):
        # Populate cache
        client.get(reverse("products:product-list"))
        assert cache.get(PRODUCT_LIST_CACHE_KEY) is not None

        # Save product — should trigger signal and clear cache
        product.name = "Updated Mouse"
        product.save()

        assert cache.get(PRODUCT_LIST_CACHE_KEY) is None

    def test_product_delete_invalidates_cache(self, client, product):
        # Populate cache
        client.get(reverse("products:product-list"))
        assert cache.get(PRODUCT_LIST_CACHE_KEY) is not None

        # Delete product — should trigger signal and clear cache
        product.delete()

        assert cache.get(PRODUCT_LIST_CACHE_KEY) is None

    def test_new_product_appears_after_cache_invalidation(self, client, category):
        # Populate cache with empty product list
        client.get(reverse("products:product-list"))

        # Create new product — invalidates cache
        from inventory.models import Inventory

        p2 = Product.objects.create(
            category=category,
            name="New Product",
            price=25.00,
            is_active=True,
        )
        Inventory.objects.create(product=p2, available_stock=5)

        # Next request should return new product
        response = client.get(reverse("products:product-list"))
        names = [p["name"] for p in response.json()]
        assert "New Product" in names

    def test_detail_endpoint_bypasses_cache(self, client, product):
        """Detail requests must never be served from the list cache key."""
        url = reverse("products:product-detail", kwargs={"pk": product.id})
        response = client.get(url)
        assert response.status_code == 200
        # List cache key must not be populated by a detail request
        assert cache.get(PRODUCT_LIST_CACHE_KEY) is None

    def test_inactive_products_not_in_cache(self, client, category):
        from inventory.models import Inventory

        p_active = Product.objects.create(
            category=category,
            name="Active Product",
            price=10.00,
            is_active=True,
        )
        Inventory.objects.create(product=p_active, available_stock=5)

        p_inactive = Product.objects.create(
            category=category,
            name="Inactive Product",
            price=10.00,
            is_active=False,
        )
        Inventory.objects.create(product=p_inactive, available_stock=5)
        response = client.get(reverse("products:product-list"))
        names = [p["name"] for p in response.json()]
        assert "Active Product" in names
        assert "Inactive Product" not in names


@pytest.mark.django_db
class TestCategoryCache:

    def test_first_request_is_cache_miss(self, client, category):
        assert cache.get(CATEGORY_LIST_CACHE_KEY) is None
        client.get(reverse("products:category-list"))
        assert cache.get(CATEGORY_LIST_CACHE_KEY) is not None

    def test_category_save_invalidates_cache(self, client, category):
        # Populate cache
        client.get(reverse("products:category-list"))
        assert cache.get(CATEGORY_LIST_CACHE_KEY) is not None

        # Save category — should trigger signal and clear cache
        category.name = "Updated Electronics"
        category.save()

        assert cache.get(CATEGORY_LIST_CACHE_KEY) is None

    def test_category_delete_invalidates_cache(self, client, category):
        # Populate cache
        client.get(reverse("products:category-list"))
        assert cache.get(CATEGORY_LIST_CACHE_KEY) is not None

        # Delete category — should trigger signal and clear cache
        category.delete()

        assert cache.get(CATEGORY_LIST_CACHE_KEY) is None

    def test_cached_category_response_matches_db(self, client, category):
        response1 = client.get(reverse("products:category-list"))
        response2 = client.get(reverse("products:category-list"))
        assert response1.json() == response2.json()
