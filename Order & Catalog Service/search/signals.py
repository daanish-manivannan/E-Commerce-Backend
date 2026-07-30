from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from products.models import Product
from search.documents import ProductDocument


@receiver(post_save, sender=Product)
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


@receiver(post_delete, sender=Product)
def delete_product_from_index(sender, instance, **kwargs):
    try:
        doc = ProductDocument.get(id=instance.id)
        doc.delete()
    except Exception:
        pass
