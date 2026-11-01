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