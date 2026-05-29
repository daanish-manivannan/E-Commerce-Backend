import time
import logging
from celery import shared_task
from .models import Order

logger = logging.getLogger(__name__)

@shared_task(name="orders.tasks.fulfill_and_send_invoice_task")
def fulfill_and_send_invoice_task(order_id):
    """
    Background worker process: Takes an order ID, advances the pending state, 
    and simulates heavy out-of-process operations (PDF generation & email dispatch).
    """
    print(f"\n[CELERY] Starting background processing for Order {order_id}...")
    
    try:
        # Fetch the order from the database inside the worker process
        order = Order.objects.get(id=order_id)
        
        # 🚨 FIX: Do not change order status to 'completed' here.
        # Fulfilling the order should keep it as 'pending' until Stripe payment changes it to 'paid'.
        # 'completed' is also not a valid status in Order.STATUS_CHOICES.
        print(f"[CELERY] INFO: Processing invoice for Order {order_id} (Current status: {order.status}).")

        # --- HEAVY ASYNC PROCESSING WORKLOAD ---
        print(f"[CELERY] Simulating heavy 5-second invoice generation and email dispatch...")
        time.sleep(5)
        
        # Pull the email safely from the authenticated user relation
        user_email = order.user.email if order.user else "unknown_user@test.com"
        print(f"[CELERY] SUCCESS: PDF Invoice generated for Order {order.id}!")
        print(f"[CELERY] SUCCESS: Email sent cleanly to {user_email}!")
        
        return f"Pipeline complete for Order {order_id}"

    except Order.DoesNotExist:
        print(f"[CELERY] ERROR: Order {order_id} not found in the database.")
        return f"Order {order_id} missing."
        
    except Exception as e:
        print(f"[CELERY] CRITICAL SYSTEM FAULT: {str(e)}")
        raise e