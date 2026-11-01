from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .measurements import SPEC
from .models import Avatar, AvatarDraft, AvatarPhoto
from .serializers import AvatarPhotoSerializer, AvatarSerializer
from .services import photo_quality
from .services.photo_processing import InvalidPhoto, load_and_sanitise


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
        return Avatar.objects.filter(user=self.request.user).prefetch_related("photos")

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

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        avatar = self.get_object()
        if avatar.photos.count() >= settings.MAX_PHOTOS_PER_AVATAR:
            return Response({"detail": f"At most {settings.MAX_PHOTOS_PER_AVATAR} photos."}, status=400)
        upload = request.FILES.get("image")
        kind = request.data.get("kind", AvatarPhoto.Kind.FRONT)
        if not upload:
            return Response({"image": ["This field is required."]}, status=400)
        if kind not in AvatarPhoto.Kind.values:
            return Response({"kind": ["Invalid kind."]}, status=400)
        if upload.size > settings.MAX_PHOTO_BYTES:
            return Response({"image": ["File too large."]}, status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        try:
            img, jpeg = load_and_sanitise(upload.read())
        except InvalidPhoto as exc:
            return Response({"image": [str(exc)]}, status=400)
        quality = photo_quality.assess(img)
        if not quality["ok"]:
            return Response({"detail": "Photo quality is too low.", "issues": quality["issues"], "quality": quality},
                            status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        photo = AvatarPhoto(avatar=avatar, kind=kind, quality=quality)
        photo.file.save(f"{photo.pk}.jpg", ContentFile(jpeg), save=False)
        photo.save()
        return Response(AvatarPhotoSerializer(photo).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "delete"], url_path=r"photos/(?P<photo_id>[0-9a-f-]+)")
    def photo_detail(self, request, pk=None, photo_id=None):
        avatar = self.get_object()
        photo = get_object_or_404(AvatarPhoto, pk=photo_id, avatar=avatar)
        if request.method == "DELETE":
            photo.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        with photo.file.open("rb") as fh:
            resp = HttpResponse(fh.read(), content_type="image/jpeg")
        resp["Cache-Control"] = "private, no-store"
        return resp


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