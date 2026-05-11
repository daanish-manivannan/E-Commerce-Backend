import time
from celery import shared_task
from .models import Order

@shared_task
def generate_invoice_and_send_email(order_id):
    """
    Simulates generating a PDF and sending an email.
    Notice we pass the 'order_id', not the whole Order object. 
    Redis prefers passing simple IDs rather than complex database objects!
    """
    print(f"\n[CELERY] Starting background task for Order {order_id}...")
    
    # Simulate a heavy 5-second process (generating PDF, attaching to email, sending via SMTP)
    time.sleep(5)
    
    # We fetch the order from the database inside the background task
    try:
        order = Order.objects.get(id=order_id)
        print(f"[CELERY] SUCCESS: PDF Invoice generated for Order {order.id}!")
        print(f"[CELERY] SUCCESS: Email sent to {order.user.email}!")
    except Order.DoesNotExist:
        print(f"[CELERY] ERROR: Order {order_id} not found.")

    return f"Task complete for Order {order_id}"