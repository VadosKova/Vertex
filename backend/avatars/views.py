from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .measurements import SPEC
from .models import Avatar, AvatarDraft
from .serializers import AvatarSerializer


class MeasurementSpecView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response([
            {"key": k, "group": g, "min": lo, "max": hi, "unit": "cm", "hint": {"uk": uk, "en": en}}
            for k, (g, lo, hi, uk, en) in SPEC.items()
        ])


class AvatarViewSet(viewsets.ModelViewSet):
    serializer_class = AvatarSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Avatar.objects.filter(user=self.request.user)

    @transaction.atomic
    def perform_create(self, serializer):
        first = not Avatar.objects.filter(user=self.request.user).exists()
        serializer.save(user=self.request.user, is_default=first)
        AvatarDraft.objects.filter(user=self.request.user).delete()

    def perform_update(self, serializer):
        extra = {"measurements_updated_at": timezone.now()} if "measurements" in serializer.validated_data else {}
        serializer.save(**extra)

    @transaction.atomic
    def perform_destroy(self, instance):
        was_default, user = instance.is_default, instance.user
        instance.delete()
        if was_default:
            newest = Avatar.objects.filter(user=user).first()
            if newest:
                newest.is_default = True
                newest.save(update_fields=["is_default"])

    @action(detail=True, methods=["post"], url_path="set-default")
    @transaction.atomic
    def set_default(self, request, pk=None):
        avatar = self.get_object()
        Avatar.objects.filter(user=request.user, is_default=True).exclude(pk=avatar.pk).update(is_default=False)
        avatar.is_default = True
        avatar.save(update_fields=["is_default"])
        return Response(self.get_serializer(avatar).data)


class AvatarDraftView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request):
        draft = AvatarDraft.objects.filter(user=request.user).first()
        if not draft:
            return Response({"payload": None})
        return Response({"payload": draft.payload, "updated_at": draft.updated_at})

    def put(self, request):
        payload = request.data.get("payload")
        if not isinstance(payload, dict) or len(str(payload)) > 20000:
            return Response({"payload": ["Must be an object (max ~20 KB)."]}, status=400)
        draft, _ = AvatarDraft.objects.update_or_create(user=request.user, defaults={"payload": payload})
        return Response({"payload": draft.payload, "updated_at": draft.updated_at})

    def delete(self, request):
        AvatarDraft.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)