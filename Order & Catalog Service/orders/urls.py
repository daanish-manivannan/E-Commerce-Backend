from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import OrderViewSet, stripe_webhook # <-- Import the new view

app_name = 'orders'

router = DefaultRouter()
router.register(r'', OrderViewSet, basename='order')

urlpatterns = [
    # The webhook URL must be placed BEFORE the router URLs
    path('webhook/', stripe_webhook, name='stripe-webhook'),
    path('', include(router.urls)),
]