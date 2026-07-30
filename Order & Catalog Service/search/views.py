from elasticsearch_dsl.query import MultiMatch
from rest_framework.response import Response
from rest_framework.views import APIView
from search.documents import ProductDocument


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
