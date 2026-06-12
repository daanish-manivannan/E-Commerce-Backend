from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from django_prometheus.exports import ExportToDjangoView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def health_check(request):
    """
    Health check endpoint. Verifies DB and Redis connectivity.
    Returns 200 if all dependencies are healthy, 503 if any are down.
    """
    import redis as redis_lib
    from decouple import config
    from django.db import connection

    health = {"status": "healthy", "services": {}}
    status_code = 200

    # Check PostgreSQL
    try:
        connection.ensure_connection()
        health["services"]["postgres"] = "healthy"
    except Exception as e:
        health["services"]["postgres"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    # Check Redis
    try:
        redis_url = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
        r = redis_lib.from_url(redis_url, decode_responses=True)
        r.ping()
        health["services"]["redis"] = "healthy"
    except Exception as e:
        health["services"]["redis"] = f"unhealthy: {str(e)}"
        health["status"] = "unhealthy"
        status_code = 503

    return JsonResponse(health, status=status_code)


urlpatterns = [
    # Prometheus Metrics — direct view so URL resolves to exactly /metrics/django
    # (using include("django_prometheus.urls") appends a /metrics sub-path, breaking the route)
    path(
        "metrics/django", ExportToDjangoView, name="prometheus-django-metrics"
    ),  # This is working
    # path("metrics/django/", include("django_prometheus.urls")), # This is not working
    # Health check
    path("health/django", health_check, name="health-check"),
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
