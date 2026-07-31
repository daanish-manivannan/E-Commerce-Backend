from elasticsearch_dsl.query import MultiMatch
from pgvector.django import CosineDistance
from products.models import Product
from rest_framework.response import Response
from rest_framework.views import APIView
from search.documents import ProductDocument
from search.semantic import get_embedding


class ProductSearchView(APIView):
    permission_classes = []  # Allow anonymous search

    def get(self, request):
        query = request.GET.get("q", "")

        search = ProductDocument.search()
        if query:
            # MultiMatch query against name and description
            search = search.query(
                MultiMatch(
                    query=query, fields=["name^3", "description"], fuzziness="AUTO"
                )
            )

        # We can add category filtering, e.g. ?category=Electronics
        category = request.GET.get("category")
        if category:
            search = search.filter("term", category=category)

        # Only show active products
        search = search.filter("term", is_active=True)

        response = search.execute()

        results = []
        for hit in response:
            results.append(
                {
                    "id": hit.id,
                    "name": hit.name,
                    "description": hit.description,
                    "price": hit.price,
                    "category": hit.category,
                    "is_active": hit.is_active,
                }
            )

        return Response(results)


class SemanticSearchView(APIView):
    permission_classes = []

    def get(self, request):
        query = request.GET.get("q", "")
        if not query:
            return Response([])

        embedding = get_embedding(query)
        if not embedding:
            return Response(
                {"error": "Failed to generate embedding for query"}, status=500
            )

        # Use CosineDistance to find most similar products
        # We order by distance ascending (closest first)
        products = (
            Product.objects.filter(is_active=True)
            .annotate(distance=CosineDistance("embedding", embedding))
            .order_by("distance")[:10]
        )

        results = []
        for product in products:
            results.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "description": product.description,
                    "price": float(product.price),
                    "category": product.category.name if product.category else None,
                    "distance": product.distance,
                }
            )

        return Response(results)
