from django.views.generic import ListView
from .models import Product

class ProductListView(ListView):
    model = Product
    template_name = 'products/product_list.html'
    context_object_name = 'products' 

    def get_queryset(self):
        return Product.objects.filter(is_active=True)