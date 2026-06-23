import logging

from django.conf import settings
from django.core.cache import cache
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer

logger = logging.getLogger("products")

PRODUCT_LIST_CACHE_KEY = "product_list_active"
CATEGORY_LIST_CACHE_KEY = "category_list_active"


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.action == "list":
            cached = cache.get(CATEGORY_LIST_CACHE_KEY)
            if cached is not None:
                logger.info("Cache HIT", extra={"key": CATEGORY_LIST_CACHE_KEY})
                return cached
            logger.info("Cache MISS", extra={"key": CATEGORY_LIST_CACHE_KEY})
            queryset = Category.objects.filter(is_active=True)
            cache.set(
                CATEGORY_LIST_CACHE_KEY,
                queryset,
                settings.CACHE_TTL_CATEGORIES,
            )
            return queryset
        return Category.objects.filter(is_active=True)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        if self.action == "list":
            cached = cache.get(PRODUCT_LIST_CACHE_KEY)
            if cached is not None:
                logger.info("Cache HIT", extra={"key": PRODUCT_LIST_CACHE_KEY})
                return cached
            logger.info("Cache MISS", extra={"key": PRODUCT_LIST_CACHE_KEY})
            queryset = Product.objects.filter(is_active=True)
            cache.set(
                PRODUCT_LIST_CACHE_KEY,
                queryset,
                settings.CACHE_TTL_PRODUCTS,
            )
            return queryset
        return Product.objects.filter(is_active=True)
