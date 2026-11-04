from django.urls import path
from . import views

urlpatterns = [
    path("notifications/", views.NotificationListView.as_view(), name="notifications"),
    path("notifications/read/", views.MarkReadView.as_view(), name="notifications-read-all"),
    path("notifications/<int:pk>/read/", views.MarkReadView.as_view(), name="notification-read"),
]