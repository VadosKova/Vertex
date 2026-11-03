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


class EvaluateView(APIView):
    def post(self, request):
        ser = s.EvaluateRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        avatar = _avatar_for(request, d.get("avatar_id"))
        product = get_object_or_404(visible_products(request.user), pk=d["product_id"])
        lang = _lang(request, d.get("lang"))
        result, err = _evaluate(product, avatar, d.get("size"), lang)
        if err:
            return err
        if result is None:
            return Response({"detail": "Product has no size chart."}, status=422)
        all_sizes = [{"label": r["label"], "score": r["score"], "fits": r["fits"]}
                     for r in evaluate_product(product, avatar.full_measurements()[0], lang)]
        return Response({"product_id": product.pk, "avatar_id": str(avatar.pk), "estimated_fields":
                         avatar.full_measurements()[1], "result": result, "sizes": all_sizes})


def serialize_session(session, lang):
    measurements = session.avatar.full_measurements()[0]
    items = []
    for item in session.items.select_related("product").prefetch_related("product__sizes"):
        size = next((x for x in item.product.sizes.all() if x.label == item.size_label), None)
        evaluation = evaluate_size(size, measurements, item.product.fabric_stretch, lang) if size else None
        items.append({"id": item.pk, "product_id": item.product_id, "title": item.product.title,
                      "size": item.size_label, "visible": item.visible, "layer": item.layer,
                      "garment_model_url": item.product.garment_model_url, "fit": evaluation})
    return {"id": str(session.pk), "avatar_id": str(session.avatar_id), "items": items}