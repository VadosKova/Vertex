from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DeviceToken, Notification

MAX_DEVICES_PER_USER = 10


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "body", "action", "data", "read", "created_at")


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["unread_count"] = Notification.objects.filter(user=self.request.user, read=False).count()
        return response


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user).order_by("-created_at", "-id")
        if self.request.query_params.get("unread", "").lower() in ("1", "true", "yes"):
            qs = qs.filter(read=False)
        return qs


class MarkReadView(APIView):
    def post(self, request, pk=None):
        qs = Notification.objects.filter(user=request.user)
        if pk is not None:
            if not qs.filter(pk=pk).exists():
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(pk=pk)
        updated = qs.filter(read=False).update(read=True)
        return Response({"updated": updated})


class DeviceSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=8, max_length=4096)
    platform = serializers.ChoiceField(choices=["android", "ios"], required=False, default="android")


class DeviceView(APIView):
    def post(self, request):
        ser = DeviceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        device, created = DeviceToken.objects.update_or_create(
            token=d["token"], defaults={"user": request.user, "platform": d["platform"]})
        extra = list(DeviceToken.objects.filter(user=request.user).order_by("-last_seen_at", "-id")
                     .values_list("pk", flat=True)[MAX_DEVICES_PER_USER:])
        if extra:
            DeviceToken.objects.filter(pk__in=extra).delete()
        return Response({"registered": True}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def delete(self, request):
        ser = DeviceSerializer(data={**request.data, "platform": "android"})
        ser.is_valid(raise_exception=True)
        DeviceToken.objects.filter(user=request.user, token=ser.validated_data["token"]).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)