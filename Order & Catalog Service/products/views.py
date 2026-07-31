import logging

from django.conf import settings
from django.core.cache import cache
from pgvector.django import CosineDistance
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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

    @action(detail=True, methods=["get"], url_path="similar")
    def similar(self, request, pk=None):
        product = self.get_object()

        if not product.embedding:
            return Response(
                {"error": "This product does not have an embedding yet."}, status=400
            )

        # Find 5 most similar products, excluding the product itself
        similar_products = (
            Product.objects.filter(is_active=True)
            .exclude(id=product.id)
            .annotate(distance=CosineDistance("embedding", product.embedding))
            .order_by("distance")[:5]
        )

        serializer = self.get_serializer(similar_products, many=True)
        return Response(serializer.data)
