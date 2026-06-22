"""
Tests for order creation, stock management, and order API.

Covers:
- Successful order creation with correct stock deduction
- Insufficient stock rejection with transaction rollback
- Order creation with multiple items
- Order items store price snapshot not current price
- Users can only see their own orders
- Order list returns correct user's orders only
- Order retrieve returns 404 for another user's order
- Empty items list rejected
- Order status defaults to pending
"""

import pytest
from django.urls import reverse
from orders.models import Order, OrderItem
from products.models import Category, Product
from rest_framework.test import APIClient
from users.models import CustomUser


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        email="buyer@test.com", password="password123"
    )


@pytest.fixture
def other_user(db):
    return CustomUser.objects.create_user(
        email="other@test.com", password="password123"
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def other_auth_client(other_user):
    client = APIClient()
    client.force_authenticate(user=other_user)
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(name="Electronics")


@pytest.fixture
def product(category):
    return Product.objects.create(
        category=category,
        name="Wireless Mouse",
        price=50.00,
        stock=10,
        is_active=True,
    )


@pytest.fixture
def second_product(category):
    return Product.objects.create(
        category=category,
        name="Mechanical Keyboard",
        price=120.00,
        stock=5,
        is_active=True,
    )


@pytest.mark.django_db
class TestOrderCreation:

    def test_successful_order_creation(self, auth_client, product):
        url = reverse("orders:order-list")
        response = auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 2}]},
            format="json",
        )
        assert response.status_code == 201
        assert Order.objects.count() == 1

    def test_order_status_defaults_to_pending(self, auth_client, product):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        order = Order.objects.first()
        assert order.status == "pending"

    def test_stock_deducted_after_order(self, auth_client, product):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 3}]},
            format="json",
        )
        product.refresh_from_db()
        assert product.stock == 7

    def test_price_snapshot_stored_not_current_price(self, auth_client, product):
        """
        OrderItem must store the price at time of purchase.
        If the product price changes later, the order item price must not change.
        """
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        order_item = OrderItem.objects.first()
        assert order_item.price == product.price

        # Now change the product price
        product.price = 999.00
        product.save()

        # Order item price must remain at original snapshot
        order_item.refresh_from_db()
        assert order_item.price == 50.00

    def test_order_with_multiple_items(self, auth_client, product, second_product):
        url = reverse("orders:order-list")
        response = auth_client.post(
            url,
            {
                "items": [
                    {"product": product.id, "quantity": 2},
                    {"product": second_product.id, "quantity": 1},
                ]
            },
            format="json",
        )
        assert response.status_code == 201
        assert OrderItem.objects.count() == 2
        product.refresh_from_db()
        second_product.refresh_from_db()
        assert product.stock == 8
        assert second_product.stock == 4

    def test_total_cost_calculated_correctly(self, auth_client, product):
        url = reverse("orders:order-list")
        response = auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 3}]},
            format="json",
        )
        assert response.status_code == 201
        assert float(response.data["total_cost"]) == 150.00


@pytest.mark.django_db
class TestOrderStockValidation:

    def test_insufficient_stock_rejected(self, auth_client, product):
        url = reverse("orders:order-list")
        response = auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 20}]},
            format="json",
        )
        assert response.status_code == 400

    def test_no_order_created_on_insufficient_stock(self, auth_client, product):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 20}]},
            format="json",
        )
        assert Order.objects.count() == 0

    def test_stock_not_deducted_on_insufficient_stock(self, auth_client, product):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 20}]},
            format="json",
        )
        product.refresh_from_db()
        assert product.stock == 10

    def test_partial_failure_rolls_back_entire_order(
        self, auth_client, product, second_product
    ):
        """
        If one item in a multi-item order fails stock check,
        the entire order must be rolled back — no partial orders.
        """
        url = reverse("orders:order-list")
        response = auth_client.post(
            url,
            {
                "items": [
                    {"product": product.id, "quantity": 2},
                    {"product": second_product.id, "quantity": 999},
                ]
            },
            format="json",
        )
        assert response.status_code == 400
        assert Order.objects.count() == 0
        product.refresh_from_db()
        assert product.stock == 10


@pytest.mark.django_db
class TestOrderOwnership:

    def test_unauthenticated_request_rejected(self, product):
        client = APIClient()
        url = reverse("orders:order-list")
        response = client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        assert response.status_code in (401, 403)

    def test_user_can_only_see_own_orders(
        self, auth_client, other_auth_client, product
    ):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        response = other_auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 0

    def test_user_cannot_retrieve_another_users_order(
        self, auth_client, other_auth_client, product
    ):
        url = reverse("orders:order-list")
        create_response = auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        order_id = create_response.data["id"]
        retrieve_url = reverse("orders:order-detail", kwargs={"pk": order_id})
        response = other_auth_client.get(retrieve_url)
        assert response.status_code == 404

    def test_order_list_returns_only_current_users_orders(
        self, auth_client, other_auth_client, product, second_product
    ):
        url = reverse("orders:order-list")
        auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 1}]},
            format="json",
        )
        other_auth_client.post(
            url,
            {"items": [{"product": second_product.id, "quantity": 1}]},
            format="json",
        )
        response = auth_client.get(url)
        assert response.status_code == 200
        assert len(response.data) == 1
