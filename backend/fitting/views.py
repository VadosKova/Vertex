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
        if session.items.filter(product=product).exists():
            return Response({"detail": "This item is already on the avatar."}, status=status.HTTP_409_CONFLICT)
        layer = session.items.count()
        if layer >= MAX_ITEMS_PER_SESSION:
            return Response({"detail": f"At most {MAX_ITEMS_PER_SESSION} items per session."}, status=400)
        TryOnItem.objects.create(session=session, product=product, size_label=result["label"], layer=layer)
        return Response(serialize_session(session, _lang(request)), status=status.HTTP_201_CREATED)


class SessionItemDetailView(APIView):
    def _item(self, request, pk, item_id):
        return get_object_or_404(TryOnItem.objects.select_related("session__avatar", "product"),
                                 pk=item_id, session_id=pk, session__user=request.user)

    def patch(self, request, pk, item_id):
        item = self._item(request, pk, item_id)
        ser = s.ItemUpdateSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        size = ser.validated_data.get("size_label")
        if size and not item.product.sizes.filter(label__iexact=size).exists():
            return Response({"size_label": ["Unknown size for this product."]}, status=400)
        ser.save()
        return Response(serialize_session(item.session, _lang(request)))

    def delete(self, request, pk, item_id):
        self._item(request, pk, item_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)