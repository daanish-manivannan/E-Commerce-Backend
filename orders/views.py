import stripe
from django.conf import settings
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Order
from .serializers import OrderSerializer

# Initialize the Stripe library with your secret key
stripe.api_key = settings.STRIPE_SECRET_KEY

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).order_by('-created_at')

    # This creates a new URL route: POST /api/orders/<id>/create-checkout-session/
    @action(detail=True, methods=['post'], url_path='create-checkout-session')
    def create_checkout_session(self, request, pk=None):
        order = self.get_object()

        # 1. Prevent users from paying for an order that is already paid or cancelled
        if order.status != 'pending':
            return Response(
                {"error": f"Order cannot be paid. Current status is {order.status}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2. Format the order items into the exact JSON structure Stripe demands
        line_items = []
        for item in order.items.all():
            line_items.append({
                'price_data': {
                    'currency': 'usd', # Change to 'inr' or your preferred currency if needed
                    'product_data': {
                        'name': item.product.name,
                    },
                    # Stripe expects prices in CENTS (or the smallest currency unit)
                    # So $50.00 becomes 5000
                    'unit_amount': int(item.price * 100), 
                },
                'quantity': item.quantity,
            })

        try:
            # 3. Create the secure session on Stripe's servers
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=line_items,
                mode='payment',
                # Where Stripe sends the user after they finish
                success_url=request.build_absolute_uri('/api/orders/?success=true'),
                cancel_url=request.build_absolute_uri('/api/orders/?canceled=true'),
                # CRITICAL: We tag the session with YOUR Order ID so we can identify it later!
                client_reference_id=str(order.id) 
            )
            
            # 4. Return the secure Stripe URL to your frontend
            return Response({'checkout_url': checkout_session.url})
            
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

# We use a standard Django view here instead of DRF because Stripe 
# strictly requires the RAW request body to verify the cryptographic signature.
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    # # --- ADD THIS DEBUG BLOCK ---
    # print("\n" + "="*50)
    # print(f"[DEBUG] Django's Secret Key: '{settings.STRIPE_WEBHOOK_SECRET}'")
    # print(f"[DEBUG] Stripe Signature Header exists: {bool(sig_header)}")
    # print("="*50 + "\n")
    # # ----------------------------
    
    event = None

    try:
        # Verify the payload was actually sent by Stripe
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature (someone trying to hack your webhook)
        return HttpResponse(status=400)

    # If it is a successful checkout event, update the database!
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        
        # FIX: Use dot notation for Stripe objects in the latest library version
        order_id = session.client_reference_id

        if order_id:
            try:
                order = Order.objects.get(id=order_id)
                order.status = 'paid' # THE CRITICAL UPDATE
                order.save()
                print(f"\n[WEBHOOK] ✅ SUCCESS: Order {order_id} has been marked as PAID!\n")
            except Order.DoesNotExist:
                print(f"\n[WEBHOOK] ❌ ERROR: Order {order_id} not found.\n")

    # Always return a 200 OK so Stripe knows we received it
    return HttpResponse(status=200)