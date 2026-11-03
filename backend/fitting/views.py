from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from avatars.models import Avatar
from catalog.views import visible_products

from .engine import evaluate_product, evaluate_size, recommend_size
from .models import TryOnItem, TryOnSession
from . import serializers as s


MAX_ITEMS_PER_SESSION = 10


def _lang(request, explicit=None):
    return explicit or request.query_params.get("lang") or getattr(request.user, "language", "uk")


def _avatar_for(request, avatar_id):
    qs = Avatar.objects.filter(user=request.user)
    return get_object_or_404(qs, pk=avatar_id) if avatar_id else get_object_or_404(qs, is_default=True)


def _evaluate(product, avatar, size, lang):
    measurements = avatar.full_measurements()[0]
    if size:
        match = next((sz for sz in product.sizes.all() if sz.label.upper() == size.upper()), None)
        if match is None:
            return None, Response({"size": ["Unknown size for this product."]}, status=400)
        return evaluate_size(match, measurements, product.fabric_stretch, lang), None
    return recommend_size(product, measurements, lang), None