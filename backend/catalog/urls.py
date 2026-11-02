from django.urls import path
from . import views

urlpatterns = [
    path("catalog/categories/", views.CategoryListView.as_view(), name="categories"),
    path("catalog/products/", views.ProductListView.as_view(), name="products"),
    path("catalog/products/import/", views.ProductImportView.as_view(), name="product-import"),
    path("catalog/products/<int:pk>/", views.ProductDetailView.as_view(), name="product-detail"),
]