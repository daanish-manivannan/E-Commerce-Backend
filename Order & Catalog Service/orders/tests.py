# Create your tests here.
import pytest
from django.urls import reverse
from orders.models import Order, OrderItem
from products.models import Category, Product
from rest_framework.test import APIClient
from users.models import CustomUser


@pytest.mark.django_db
class TestOrderAPI:

    @pytest.fixture
    def setup_data(self):
        # 1. Create a fake user and an authenticated API client
        user = CustomUser.objects.create_user(
            email="buyer@test.com", password="password123"
        )
        client = APIClient()
        client.force_authenticate(user=user)

        # 2. Create a fake category and product for them to buy
        category = Category.objects.create(name="Electronics")
        product = Product.objects.create(
            category=category,
            name="Wireless Mouse",
            price=50.00,
            stock=10,  # We start with exactly 10 in stock
        )

        return {"user": user, "product": product, "client": client}

    def test_successful_checkout_and_stock_deduction(self, setup_data):
        client = setup_data["client"]
        product = setup_data["product"]
        url = reverse("orders:order-list")

        # The user tries to buy 2 mice
        payload = {"items": [{"product": product.id, "quantity": 2}]}

        response = client.post(url, payload, format="json")

        # Assert 1: The API accepted the order
        assert response.status_code == 201

        # Assert 2: The Order was saved to the database correctly
        assert Order.objects.count() == 1
        order = Order.objects.first()
        assert order.user == setup_data["user"]
        assert order.total_cost == 100.00  # 2 mice * $50

        # Assert 3: The price was successfully locked into the OrderItem table
        order_item = OrderItem.objects.first()
        assert order_item.price == 50.00

        # Assert 4: THE MOST CRITICAL TEST - Stock Deduction
        product.refresh_from_db()  # We must reload the product to see the new database value
        assert product.stock == 8  # 10 original - 2 bought = 8 remaining

    def test_checkout_fails_with_insufficient_stock(self, setup_data):
        client = setup_data["client"]
        product = setup_data["product"]
        url = reverse("orders:order-list")

        # The user tries to buy 20 mice, but we only have 10
        payload = {"items": [{"product": product.id, "quantity": 20}]}

        response = client.post(url, payload, format="json")

        # Assert 1: The API rejected the order (400 Bad Request)
        assert response.status_code == 400

        # Assert 2: No order was accidentally created
        assert Order.objects.count() == 0

        # Assert 3: The stock was not accidentally deducted
        product.refresh_from_db()
        assert product.stock == 10
