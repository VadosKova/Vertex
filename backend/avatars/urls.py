from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AvatarDraftView, AvatarViewSet, MeasurementSpecView

router = DefaultRouter()
router.register("avatars", AvatarViewSet, basename="avatar")

urlpatterns = [
    path("measurements/spec/", MeasurementSpecView.as_view(), name="measurement-spec"),
    path("avatar-draft/", AvatarDraftView.as_view(), name="avatar-draft"),
] + router.urls