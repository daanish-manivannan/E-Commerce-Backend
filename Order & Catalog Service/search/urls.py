from django.urls import path

from .views import ProductSearchView, SemanticSearchView

urlpatterns = [
    path("products/", ProductSearchView.as_view(), name="product-search"),
    path("semantic/", SemanticSearchView.as_view(), name="semantic-search"),
]
