from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ("id", "kind", "title", "body", "read", "created_at")


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
        return Notification.objects.filter(user=self.request.user)


class MarkReadView(APIView):
    def post(self, request, pk=None):
        qs = Notification.objects.filter(user=request.user)
        if pk is not None:
            if not qs.filter(pk=pk).exists():
                return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            qs = qs.filter(pk=pk)
        updated = qs.filter(read=False).update(read=True)
        return Response({"updated": updated})