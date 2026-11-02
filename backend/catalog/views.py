from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from avatars.models import Avatar

from .filtering import fitting_products
from .importers import PageImportError, fetch_html, guess_category_slug, parse_product_page
from .models import Brand, Category, Product, ProductSize
from .serializers import CategorySerializer, ImportRequestSerializer, ProductSerializer


def resolve_avatar(request):
    qs = Avatar.objects.filter(user=request.user)
    avatar_id = request.query_params.get("avatar")
    if avatar_id:
        try:
            return qs.filter(pk=avatar_id).first()
        except (ValueError, DjangoValidationError):
            return None
    return qs.filter(is_default=True).first()


def visible_products(user):
    return (Product.objects.filter(Q(owner__isnull=True) | Q(owner=user))
            .select_related("brand", "category").prefetch_related("sizes"))


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all().order_by("id")
    serializer_class = CategorySerializer
    pagination_class = None


class CatalogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = CatalogPagination

    def _avatar(self):
        if not hasattr(self, "_cached_avatar"):
            self._cached_avatar = resolve_avatar(self.request)
        return self._cached_avatar

    def get_queryset(self):
        p = self.request.query_params
        qs = visible_products(self.request.user)
        if p.get("category"):
            qs = qs.filter(category__slug=p["category"])
        if p.get("brand"):
            qs = qs.filter(brand__name__iexact=p["brand"])
        if p.get("q"):
            qs = qs.filter(Q(title__icontains=p["q"]) | Q(brand__name__icontains=p["q"]))
        avatar = self._avatar()
        if avatar and p.get("personalized", "true").lower() != "false":
            qs = qs.filter(gender__in=[avatar.gender, "unisex"])
            qs = fitting_products(qs, avatar.full_measurements()[0])
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        avatar = self._avatar()
        ctx["measurements"] = avatar.full_measurements()[0] if avatar else None
        return ctx