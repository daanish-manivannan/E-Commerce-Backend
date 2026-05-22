import time
import logging
from celery import shared_task
from django.db import transaction
from .models import Order
from products.models import Product

logger = logging.getLogger(__name__)

@shared_task(name="orders.tasks.fulfill_and_send_invoice_task")
def fulfill_and_send_invoice_task(order_id):
    """
    Combined background task: Deducts product stock, marks the order 
    as completed, and simulates generating an invoice/sending an email.
    """
    print(f"\n[CELERY] Starting background fulfillment pipeline for Order {order_id}...")
    
    try:
        # --- PHASE 1: INVENTORY DEDUCTION & ORDER STATE CHANGE ---
        with transaction.atomic():
           # 🚨 FIX: Added select_for_update() here to lock the order immediately!
            # If a duplicate task tries to read this order, it will block until this transaction finishes.
            order = Order.objects.select_for_update().get(id=order_id)
            
            if order.status != "pending":
                print(f"[CELERY] Order {order_id} is already processed. Status: {order.status}")
                return f"Order {order_id} skipped."

            # Iterate through items to check and deduct stock safely
            for item in order.items.all():
                # select_for_update() locks the database row to prevent concurrent race conditions
                product = Product.objects.select_for_update().get(id=item.product.id)
                
                if product.stock >= item.quantity:
                    product.stock -= item.quantity
                    product.save()
                    print(f"[CELERY] Stock Deducted: {item.quantity} units from Product #{product.id} ({product.name})")
                else:
                    print(f"[CELERY] ERROR: Insufficient stock for Product #{product.id}")
                    order.status = "failed"
                    order.save()
                    return f"Fulfillment failed: Out of stock for Product #{product.id}."

            # Mark order as completed once inventory is secured
            order.status = "completed"
            order.save()
            print(f"[CELERY] SUCCESS: Order {order_id} status updated to COMPLETED.")

        # --- PHASE 2: INVOICING & NOTIFICATIONS (Heavy Processing) ---
        print(f"[CELERY] Simulating heavy 5-second invoice generation and email dispatch...")
        time.sleep(5)
        
        # Access the user relationship via our authenticated user instance
        user_email = order.user.email if order.user else "unknown_user@test.com"
        print(f"[CELERY] SUCCESS: PDF Invoice generated for Order {order.id}!")
        print(f"[CELERY] SUCCESS: Email sent cleanly to {user_email}!")
        
        return f"Pipeline complete for Order {order_id}"

    except Order.DoesNotExist:
        print(f"[CELERY] ERROR: Order {order_id} not found in the database.")
        return f"Order {order_id} not found."
    except Exception as e:
        print(f"[CELERY] CRITICAL SYSTEM FAULT: {str(e)}")
        raise e