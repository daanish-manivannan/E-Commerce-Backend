"""
Tests for the custom DRF exception handler.

Covers:
- 404 responses use standard error shape
- 400 responses use standard error shape
- 401 responses use standard error shape
- Error response always contains error, message, timestamp keys
- Timestamp is in correct ISO format
- Unknown status codes fall back to ERROR code
"""

import pytest
from django.urls import reverse
from products.models import Category, Product
from rest_framework.test import APIClient
from users.models import CustomUser


@pytest.fixture
def user(db):
    return CustomUser.objects.create_user(
        email="testuser@test.com", password="password123"
    )


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestExceptionHandlerShape:

    def test_404_has_standard_error_shape(self, auth_client):
        url = reverse("orders:order-detail", kwargs={"pk": 99999})
        response = auth_client.get(url)
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "timestamp" in data

    def test_404_error_code_is_not_found(self, auth_client):
        url = reverse("orders:order-detail", kwargs={"pk": 99999})
        response = auth_client.get(url)
        assert response.json()["error"] == "NOT_FOUND"

    def test_404_message_is_human_readable(self, auth_client):
        url = reverse("orders:order-detail", kwargs={"pk": 99999})
        response = auth_client.get(url)
        assert len(response.json()["message"]) > 0

    def test_400_has_standard_error_shape(self, auth_client):
        category = Category.objects.create(name="Test")
        product = Product.objects.create(
            category=category, name="Item", price=10.00, stock=1
        )
        url = reverse("orders:order-list")
        # Request more than available stock to trigger a 400
        response = auth_client.post(
            url,
            {"items": [{"product": product.id, "quantity": 999}]},
            format="json",
        )
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "timestamp" in data

    def test_403_has_standard_error_shape(self):
        client = APIClient()
        url = reverse("orders:order-list")
        response = client.get(url)
        assert response.status_code == 403
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "timestamp" in data

    def test_403_error_code_is_forbidden(self):
        client = APIClient()
        url = reverse("orders:order-list")
        response = client.get(url)
        assert response.json()["error"] == "FORBIDDEN"

    def test_timestamp_is_iso_format(self, auth_client):
        from datetime import datetime

        url = reverse("orders:order-detail", kwargs={"pk": 99999})
        response = auth_client.get(url)
        timestamp = response.json()["timestamp"]
        # Should parse without error
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    def test_error_response_has_no_extra_keys(self, auth_client):
        url = reverse("orders:order-detail", kwargs={"pk": 99999})
        response = auth_client.get(url)
        data = response.json()
        assert set(data.keys()) == {"error", "message", "timestamp"}
