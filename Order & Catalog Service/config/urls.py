from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),
    # path('products/', include('products.urls', namespace='products')),
    # FIX: Prepended 'api/' to keep catalog routing unified under Nginx
    path("api/products/", include("products.urls", namespace="products")),
    # User App Endpoints
    path("api/users/", include("users.urls", namespace="users")),
    # NEW: Order API Endpoints
    path("api/orders/", include("orders.urls", namespace="orders")),
    # JWT Auth Endpoints
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
]
