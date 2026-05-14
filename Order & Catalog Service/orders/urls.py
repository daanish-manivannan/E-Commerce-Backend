from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, stripe_webhook, UserSyncView

# Namespace for reverse URL looking (matches config/urls.py)
app_name = 'orders'

# Initialize the router for standard RESTful Order routes
router = DefaultRouter()
router.register(r'', OrderViewSet, basename='order')

urlpatterns = [
    # 1. Stripe Webhook (Full Path: /api/orders/webhook/)
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    
    # 2. Internal User Sync (Full Path: /api/orders/users/sync/)
    # This is the endpoint FastAPI hits after a successful registration.
    path('users/sync/', UserSyncView.as_view(), name='user-sync'),
    
    # 3. Router URLs (Full Path: /api/orders/)
    # This handles list, create, retrieve, etc. for Orders.
    path('', include(router.urls)),
]