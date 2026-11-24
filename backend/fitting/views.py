from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from avatars.models import Avatar
from catalog.views import visible_products

from .engine import evaluate_product, evaluate_size, recommend_size
from .models import TryOnItem, TryOnSession
from . import serializers as s


def max_layers():
    return getattr(settings, "MAX_TRYON_LAYERS", 4)


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
        measurements = avatar.full_measurements()[0]
        rec = recommend_size(product, measurements, lang)
        recommended = {"label": rec["label"], "compatibility": rec["compatibility"], "fits": rec["fits"]} if rec else None
        all_sizes = [{"label": r["label"], "score": r["score"], "fits": r["fits"],
                      "compatibility": r["compatibility"]}
                     for r in evaluate_product(product, avatar.full_measurements()[0], lang)]
        return Response({"product_id": product.pk, "avatar_id": str(avatar.pk), "estimated_fields":
                         avatar.full_measurements()[1], "approximate": product.size_chart_source == "default",
                         "recommended": recommended, "result": result, "sizes": all_sizes})


def serialize_session(session, lang):
    measurements = session.avatar.full_measurements()[0]
    items = []
    for item in session.items.select_related("product__brand").prefetch_related("product__sizes"):
        product = item.product
        size = next((x for x in product.sizes.all() if x.label == item.size_label), None)
        evaluation = evaluate_size(size, measurements, product.fabric_stretch, lang) if size else None
        rec = recommend_size(product, measurements, lang)
        items.append({"id": item.pk, "product_id": item.product_id, "title": product.title,
                      "brand": product.brand.name, "image_url": product.image_url, "shop_url": product.source_url,
                      "price": float(product.price) if product.price is not None else None,
                      "currency": product.currency, "size": item.size_label,
                      "recommended_size": rec["label"] if rec else None, "visible": item.visible,
                      "layer": item.layer, "garment_model_url": product.garment_model_url,
                      "approximate": product.size_chart_source == "default", "fit": evaluation})
    return {"id": str(session.pk), "avatar_id": str(session.avatar_id), "layers_limit": max_layers(),
            "layers_count": len(items), "visible_count": sum(1 for i in items if i["visible"]), "items": items}


class SessionListCreateView(APIView):
    def get(self, request):
        sessions = TryOnSession.objects.filter(user=request.user)[:20]
        return Response([{"id": str(x.pk), "avatar_id": str(x.avatar_id), "created_at": x.created_at} for x in sessions])

    def post(self, request):
        ser = s.SessionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        avatar = _avatar_for(request, ser.validated_data.get("avatar_id"))
        session = TryOnSession.objects.create(user=request.user, avatar=avatar)
        return Response(serialize_session(session, _lang(request)), status=status.HTTP_201_CREATED)


class SessionDetailView(APIView):
    def get(self, request, pk):
        session = get_object_or_404(TryOnSession.objects.select_related("avatar"), pk=pk, user=request.user)
        return Response(serialize_session(session, _lang(request)))

    def delete(self, request, pk):
        get_object_or_404(TryOnSession, pk=pk, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SessionItemsView(APIView):
    def post(self, request, pk):
        session = get_object_or_404(TryOnSession.objects.select_related("avatar"), pk=pk, user=request.user)
        ser = s.ItemCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = get_object_or_404(visible_products(request.user), pk=ser.validated_data["product_id"])
        result, err = _evaluate(product, session.avatar, ser.validated_data.get("size"), "uk")
        if err:
            return err
        if result is None:
            return Response({"detail": "Product has no size chart."}, status=422)
        with transaction.atomic():
            TryOnSession.objects.select_for_update().get(pk=session.pk)
            if session.items.filter(product=product).exists():
                return Response({"code": "already_added", "detail": "This item is already on the avatar."},
                                status=status.HTTP_409_CONFLICT)
            layer = session.items.count()
            if layer >= max_layers():
                return Response({"code": "layer_limit", "limit": max_layers(),
                                 "detail": f"At most {max_layers()} items on the avatar."}, status=400)
            TryOnItem.objects.create(session=session, product=product, size_label=result["label"], layer=layer)
        return Response(serialize_session(session, _lang(request)), status=status.HTTP_201_CREATED)


def _renumber(session, ordered=None):
    items = ordered if ordered is not None else list(session.items.order_by("layer", "id"))
    for index, item in enumerate(items):
        if item.layer != index:
            TryOnItem.objects.filter(pk=item.pk).update(layer=index)


class SessionItemDetailView(APIView):
    def _item(self, request, pk, item_id):
        return get_object_or_404(TryOnItem.objects.select_related("session__avatar", "product"),
                                 pk=item_id, session_id=pk, session__user=request.user)

    def patch(self, request, pk, item_id):
        item = self._item(request, pk, item_id)
        ser = s.ItemUpdateSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        label = None
        if "size_label" in data:
            match = next((x for x in item.product.sizes.all() if x.label.upper() == data["size_label"].upper()), None)
            if match is None:
                return Response({"size_label": ["Unknown size for this product."]}, status=400)
            label = match.label
        with transaction.atomic():
            items = list(item.session.items.order_by("layer", "id"))
            if "layer" in data:
                if not 0 <= data["layer"] < len(items):
                    return Response({"layer": [f"Must be between 0 and {len(items) - 1}."]}, status=400)
                items = [i for i in items if i.pk != item.pk]
                items.insert(data["layer"], item)
            if "visible" in data:
                item.visible = data["visible"]
            if label is not None:
                item.size_label = label
            item.save(update_fields=["visible", "size_label"])
            _renumber(item.session, items)
        return Response(serialize_session(item.session, _lang(request)))

    def delete(self, request, pk, item_id):
        item = self._item(request, pk, item_id)
        session = item.session
        with transaction.atomic():
            item.delete()
            _renumber(session)
        return Response(status=status.HTTP_204_NO_CONTENT)