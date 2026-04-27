import pytest
from .models import Product, Category

@pytest.mark.django_db
def test_create_product():
    # 1. Create the required category first
    category = Category.objects.create(name="Electronics")
    
    # 2. Assign that category to the new product
    product = Product.objects.create(
        category=category,
        name="Mechanical Keyboard",
        description="Clicky switches",
        price=120.50
    )
    
    assert product.name == "Mechanical Keyboard"
    assert product.price == 120.50
    assert product.is_active is True