from django.db import models
from products.models import Product


class Inventory(models.Model):
    product = models.OneToOneField(
        Product, related_name="inventory", on_delete=models.CASCADE
    )
    available_stock = models.PositiveIntegerField(default=0)
    reserved_stock = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Inventory for {self.product.name} ({self.available_stock} available, {self.reserved_stock} reserved)"


class StockTransaction(models.Model):
    TRANSACTION_TYPES = (
        ("restock", "Restock"),
        ("reserve", "Reserve"),
        ("consume", "Consume"),
        ("cancel_reservation", "Cancel Reservation"),
        ("manual_adjustment", "Manual Adjustment"),
    )

    inventory = models.ForeignKey(
        Inventory, related_name="transactions", on_delete=models.CASCADE
    )
    transaction_type = models.CharField(max_length=25, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField()  # Positive or negative depending on the operation
    order_id = models.IntegerField(
        null=True, blank=True
    )  # To trace back to a specific order
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_transaction_type_display()} of {self.quantity} for {self.inventory.product.name}"
