import os
import stripe
import logging
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model  # Added for Shadow User
from rest_framework import viewsets, status, permissions  # Added permissions
from rest_framework.views import APIView  # Added for Sync View
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction

from .models import Order
from .serializers import OrderSerializer

# Get the User model dynamically
User = get_user_model()

# --- PRO LOGGING CONFIGURATION ---
logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# --- SHADOW USER SYNC VIEW ---
class UserSyncView(APIView):
    """
    Internal-only endpoint to sync users from the Identity Service.
    Ensures a 'Shadow User' exists in the Django DB for order association.
    """
    # AllowAny because we use a custom X-Internal-Secret header for security
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # 1. Security Handshake
        internal_secret = request.headers.get("X-Internal-Secret")
        expected_secret = os.getenv("SECRET_KEY")

        if not internal_secret or internal_secret != expected_secret:
            logger.warning("🚫 Unauthorized sync attempt: Secret mismatch or missing.")
            return Response(
                {"detail": "Unauthorized internal service call"}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # 2. Data Extraction
        email = request.data.get("email")
        if not email:
            return Response({"detail": "Email missing"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 3. Database Operation (Wrapped in a transaction for safety)
            with transaction.atomic():
                # get_or_create handles the check and the save in one step
                user, created = User.objects.get_or_create(email=email)
                
                if created:
                    # Shadow users don't need passwords since they auth via FastAPI
                    user.set_unusable_password()
                    user.save()
                    logger.info(f"✅ Created NEW Shadow User: {email} (ID: {user.id})")
                else:
                    logger.info(f"ℹ️ Shadow User already exists: {email} (ID: {user.id})")

                # --- CRITICAL DEBUG LOGGING ---
                # This will tell us if the DB Django is hitting is actually growing
                current_count = User.objects.count()
                logger.info(f"📊 Django Internal User Count: {current_count}")

                return Response({
                    "message": "User sync successful",
                    "created": created,
                    "id": user.id,
                    "current_db_count": current_count
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"❌ Critical Error during User Sync for {email}: {str(e)}")
            return Response(
                {"detail": "Internal database error during sync"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

# --- ORDER MANAGEMENT VIEWSET ---
class OrderViewSet(viewsets.ModelViewSet):
    """
    Standard API for managing orders. Includes a custom action
    to initiate the Stripe Checkout process.
    """
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='create-checkout-session')
    def create_checkout_session(self, request, pk=None):
        order = self.get_object()

        # 1. Validation Guard
        if order.status != 'pending':
            logger.warning(f"⚠️ User {request.user.id} attempted to pay for Order {order.id} with status: {order.status}")
            return Response(
                {"error": f"Order cannot be paid. Current status is {order.status}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Construct Stripe Line Items
        line_items = []
        for item in order.items.all():
            line_items.append({
                'price_data': {
                    'currency': 'usd',
                    'product_data': {
                        'name': item.product.name,
                    },
                    'unit_amount': int(item.price * 100), 
                },
                'quantity': item.quantity,
            })

        try:
            # 3. Create Stripe Session
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                success_url=request.build_absolute_uri('/api/orders/?success=true'),
                cancel_url=request.build_absolute_uri('/api/orders/?canceled=true'),
                client_reference_id=str(order.id) 
            )
            
            logger.info(f"💳 Stripe Session created for Order {order.id}")
            return Response({'checkout_url': checkout_session.url})
            
        except Exception as e:
            logger.error(f"❌ Stripe Session Creation Error: {str(e)}")
            return Response({"error": "Failed to connect to Payment Gateway"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# --- WEBHOOK HANDLING ---

@csrf_exempt
def stripe_webhook(request):
    """
    Stripe Webhook listener. 
    Verifies cryptographic signatures and updates order status.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    event = None

    # 1. Verify Signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.error("❌ Webhook Error: Invalid payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"❌ Webhook Error: Signature Verification Failed - {e}")
        return HttpResponse(status=400)

    # 2. Process Business Logic
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        order_id = session.get('client_reference_id')

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                # Only update if pending to prevent race conditions
                if order.status == 'pending':
                    order.status = 'paid'
                    order.save()
                    logger.info(f"✅ WEBHOOK SUCCESS: Order {order_id} marked as PAID.")
                else:
                    logger.info(f"ℹ️ Webhook received for Order {order_id}, but status was already {order.status}")
            except Order.DoesNotExist:
                logger.error(f"❌ WEBHOOK DATABASE ERROR: Order {order_id} not found.")
        else:
            logger.warning("⚠️ Webhook received a session without a client_reference_id.")

    elif event['type'] == 'payment_intent.payment_failed':
        session = event['data']['object']
        logger.warning(f"🚨 Payment Failed event received for Session {session.get('id')}")

    # Always return 200 to Stripe
    return HttpResponse(status=200)