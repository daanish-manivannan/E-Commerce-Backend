from rest_framework import serializers
from .models import Order, OrderItem
from products.models import Product
from .tasks import generate_invoice_and_send_email

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    # We make price read-only so hackers can't send {"price": 0.01} in their payload
    price = serializers.ReadOnlyField() 

    class Meta:
        model = OrderItem
        fields = ['product', 'product_name', 'quantity', 'price']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True) # Nested relationship
    total_cost = serializers.ReadOnlyField()
    status = serializers.ReadOnlyField() # Status is strictly managed by the backend

    class Meta:
        model = Order
        fields = ['id', 'status', 'created_at', 'total_cost', 'items']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        
        # --- 1. PRE-CHECK PHASE ---
        # Verify ALL stock before saving anything to the database!
        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            if product.stock < quantity:
                # If even one item fails, the whole request is rejected here.
                raise serializers.ValidationError(f"Not enough stock for {product.name}. Only {product.stock} left.")
        
        # --- 2. CREATION PHASE ---
        # If the code reaches this line, we know we have enough stock for everything.    
        order = Order.objects.create(user=self.context['request'].user, **validated_data)

        for item_data in items_data:
            product = item_data['product']
            quantity = item_data['quantity']
            
            # Deduct the stock
            product.stock -= quantity
            product.save()

            # Create the OrderItem locking in the official price
            OrderItem.objects.create(
                order=order,
                product=product,
                price=product.price,
                quantity=quantity
            )
            
        # --- 3. BACKGROUND TASKS ---
        # The .delay() method magically sends this to Redis instead of running it right now!
        generate_invoice_and_send_email.delay(order.id)
        return order