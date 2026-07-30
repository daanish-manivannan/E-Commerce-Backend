from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from inventory.services import reserve_stock
from rest_framework import serializers

from .models import Order, OrderItem
from .tasks import fulfill_and_send_invoice_task


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source="product.name")
    price = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ["product", "product_name", "quantity", "price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    total_cost = serializers.ReadOnlyField()
    status = serializers.ReadOnlyField()

    class Meta:
        model = Order
        fields = ["id", "status", "created_at", "total_cost", "items"]

    def create(self, validated_data):
        items_data = validated_data.pop("items")

        # 📌 1. Open an atomic database transaction context block
        with transaction.atomic():
            # Create the parent order shell linked to the context request user
            order = Order.objects.create(
                user=self.context["request"].user, **validated_data
            )

            for item_data in items_data:
                product_instance = item_data["product"]
                quantity = item_data["quantity"]

                product = product_instance

                # 📌 3. Atomic Evaluation & Reserve Combined
                # Use inventory service to securely reserve stock
                try:
                    reserve_stock(product.id, quantity, order.id)
                except DjangoValidationError as e:
                    exc = (
                        serializers.ValidationError(e.message)
                        if hasattr(e, "message")
                        else serializers.ValidationError(e.messages)
                    )
                    raise exc from e

                # Lock in the line-item snapshot invoice metadata
                OrderItem.objects.create(
                    order=order, product=product, price=product.price, quantity=quantity
                )

        # 📌 4. BACKGROUND TASKS (Triggered only AFTER transaction safely commits)
        # We pass it to Celery. .delay() drops a message straight into Redis!
        transaction.on_commit(lambda: fulfill_and_send_invoice_task.delay(order.id))

        return order
