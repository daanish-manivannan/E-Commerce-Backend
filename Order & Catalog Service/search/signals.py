import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from products.models import Product
from products.tasks import generate_product_embedding
from search.documents import ProductDocument
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Product)
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def index_product(sender, instance, **kwargs):
    doc = ProductDocument(
        meta={"id": instance.id},
        id=instance.id,
        name=instance.name,
        description=instance.description,
        price=float(instance.price),
        category=instance.category.name,
        is_active=instance.is_active,
    )
    doc.save()

    # Generate Vector Embedding for Semantic Search
    generate_product_embedding.delay(instance.id)


@receiver(post_delete, sender=Product)
@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def delete_product_from_index(sender, instance, **kwargs):
    try:
        doc = ProductDocument.get(id=instance.id)
        doc.delete()
    except Exception:
        pass
