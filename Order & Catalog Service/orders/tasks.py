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
        
        # Advance the order state out-of-process if it hasn't been handled yet
        if order.status == 'pending':
            order.status = 'completed'
            order.save()
            print(f"[CELERY] SUCCESS: Order {order_id} status updated to COMPLETED.")
        else:
            print(f"[CELERY] Info: Order {order_id} already has status: {order.status}")

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