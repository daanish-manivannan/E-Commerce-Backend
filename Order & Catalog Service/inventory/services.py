from config.events import publisher
from django.core.exceptions import ValidationError
from django.db import transaction
from products.models import Product

from .models import Inventory, StockTransaction


def get_inventory(product_id):
    """Get or create inventory for a product."""
    product = Product.objects.get(id=product_id)
    inventory, created = Inventory.objects.get_or_create(product=product)
    return inventory


@transaction.atomic
def reserve_stock(product_id, quantity, order_id=None):
    """
    Reserves stock for an order.
    Uses select_for_update to prevent race conditions.
    """
    try:
        inventory = Inventory.objects.select_for_update().get(product_id=product_id)
    except Inventory.DoesNotExist as err:
        raise ValidationError(f"Inventory not found for product {product_id}") from err

    if inventory.available_stock < quantity:
        raise ValidationError(
            f"Not enough stock for {inventory.product.name}. Only {inventory.available_stock} left."
        )

    # Move from available to reserved
    inventory.available_stock -= quantity
    inventory.reserved_stock += quantity
    inventory.save()

    # Record the transaction
    StockTransaction.objects.create(
        inventory=inventory,
        transaction_type="reserve",
        quantity=quantity,
        order_id=order_id,
        notes=f"Reserved {quantity} for order {order_id}",
    )

    # Publish inventory events if threshold crossed
    def publish_inventory_events(prod_id, prod_name, current_stock):
        if current_stock == 0:
            publisher.publish(
                "inventory.out_of_stock",
                {
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "available_stock": current_stock,
                },
            )
        elif current_stock < 5:
            publisher.publish(
                "inventory.low",
                {
                    "product_id": prod_id,
                    "product_name": prod_name,
                    "available_stock": current_stock,
                },
            )

    transaction.on_commit(
        lambda: publish_inventory_events(
            inventory.product_id, inventory.product.name, inventory.available_stock
        )
    )

    return inventory


@transaction.atomic
def confirm_reservation(product_id, quantity, order_id=None):
    """
    Consumes reserved stock when an order is paid.
    """
    try:
        inventory = Inventory.objects.select_for_update().get(product_id=product_id)
    except Inventory.DoesNotExist as err:
        raise ValidationError(f"Inventory not found for product {product_id}") from err

    if inventory.reserved_stock < quantity:
        raise ValidationError(
            f"Cannot confirm reservation of {quantity} for {inventory.product.name}. Only {inventory.reserved_stock} reserved."
        )

    # Consume the reservation (permanently deducts from reserved, doesn't add to available)
    inventory.reserved_stock -= quantity
    inventory.save()

    StockTransaction.objects.create(
        inventory=inventory,
        transaction_type="consume",
        quantity=quantity,
        order_id=order_id,
        notes=f"Consumed {quantity} reservation for order {order_id}",
    )

    return inventory


@transaction.atomic
def cancel_reservation(product_id, quantity, order_id=None):
    """
    Returns reserved stock back to available stock if an order is cancelled or failed.
    """
    try:
        inventory = Inventory.objects.select_for_update().get(product_id=product_id)
    except Inventory.DoesNotExist as err:
        raise ValidationError(f"Inventory not found for product {product_id}") from err

    if inventory.reserved_stock < quantity:
        raise ValidationError(
            f"Cannot cancel reservation of {quantity} for {inventory.product.name}. Only {inventory.reserved_stock} reserved."
        )

    # Move from reserved back to available
    inventory.reserved_stock -= quantity
    inventory.available_stock += quantity
    inventory.save()

    StockTransaction.objects.create(
        inventory=inventory,
        transaction_type="cancel_reservation",
        quantity=quantity,
        order_id=order_id,
        notes=f"Cancelled reservation of {quantity} for order {order_id}",
    )

    return inventory


@transaction.atomic
def add_stock(product_id, quantity, notes=""):
    """
    Adds stock manually (e.g. from supplier).
    """
    inventory = get_inventory(product_id)

    inventory.available_stock += quantity
    inventory.save()

    StockTransaction.objects.create(
        inventory=inventory, transaction_type="restock", quantity=quantity, notes=notes
    )

    return inventory
