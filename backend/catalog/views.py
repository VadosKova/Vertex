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