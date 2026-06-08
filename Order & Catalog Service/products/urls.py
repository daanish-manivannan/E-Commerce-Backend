from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet

app_name = "products"

# The Router automatically generates all the CRUD URLs for us!
router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"items", ProductViewSet, basename="product")

urlpatterns = [
    path("", include(router.urls)),
]
