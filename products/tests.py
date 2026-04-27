from django.test import TestCase

# Create your tests here.
import pytest

from .models import Product

@pytest.mark.django_db
def test_create_product():
    # 1. Action: Create a product in the test database
    product = Product.objects.create(
        name="Mechanical Keyboard",
        description="Clicky switches",
        price=120.50
    )
    
    # 2. Assertions: Prove it saved correctly
    assert product.name == "Mechanical Keyboard"
    assert product.price == 120.50
    assert product.is_active is True