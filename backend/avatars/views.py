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