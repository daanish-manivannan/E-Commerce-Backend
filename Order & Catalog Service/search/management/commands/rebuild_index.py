from django.core.management.base import BaseCommand
from elasticsearch.helpers import bulk
from elasticsearch_dsl import connections
from products.models import Product
from search.documents import ProductDocument


class Command(BaseCommand):
    help = "Rebuilds the Elasticsearch index for products."

    def handle(self, *args, **kwargs):
        self.stdout.write("Initializing Elasticsearch index...")
        # Create the index and mapping
        ProductDocument.init()

        self.stdout.write("Indexing products...")
        es = connections.get_connection()
        products = Product.objects.all().select_related("category")

        actions = [
            {
                "_index": "products",
                "_id": product.id,
                "_source": {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "price": float(product.price),
                    "category": product.category.name,
                    "is_active": product.is_active,
                },
            }
            for product in products
        ]

        if actions:
            success, _ = bulk(es, actions)
            self.stdout.write(
                self.style.SUCCESS(f"Successfully indexed {success} products.")
            )
        else:
            self.stdout.write("No products found to index.")
