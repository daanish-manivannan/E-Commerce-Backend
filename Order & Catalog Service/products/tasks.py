import logging

from celery import shared_task
from products.models import Product
from search.semantic import generate_product_embedding_text, get_embedding

logger = logging.getLogger(__name__)


@shared_task
def generate_product_embedding(product_id: int):
    try:
        product = Product.objects.get(id=product_id)
        text = generate_product_embedding_text(product)

        # Get embedding from OpenAI
        embedding = get_embedding(text)

        if embedding:
            # We use update() to avoid triggering save() signals recursively
            Product.objects.filter(id=product_id).update(embedding=embedding)
            logger.info(
                f"Successfully generated and saved embedding for Product {product_id}"
            )
        else:
            logger.warning(f"Failed to generate embedding for Product {product_id}")

    except Product.DoesNotExist:
        logger.error(f"Product {product_id} does not exist.")
    except Exception as e:
        logger.error(f"Error in generate_product_embedding task: {e}")
