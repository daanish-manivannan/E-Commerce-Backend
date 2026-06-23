import logging

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .views import CATEGORY_LIST_CACHE_KEY, PRODUCT_LIST_CACHE_KEY

logger = logging.getLogger("products")


@receiver(post_save, sender="products.Product")
@receiver(post_delete, sender="products.Product")
def invalidate_product_cache(sender, instance, **kwargs):
    cache.delete(PRODUCT_LIST_CACHE_KEY)
    logger.info(
        "Cache invalidated",
        extra={"key": PRODUCT_LIST_CACHE_KEY, "product_id": instance.id},
    )


@receiver(post_save, sender="products.Category")
@receiver(post_delete, sender="products.Category")
def invalidate_category_cache(sender, instance, **kwargs):
    cache.delete(CATEGORY_LIST_CACHE_KEY)
    logger.info(
        "Cache invalidated",
        extra={"key": CATEGORY_LIST_CACHE_KEY, "category_id": instance.id},
    )
