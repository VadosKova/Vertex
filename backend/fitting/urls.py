from django.urls import path
from . import views

urlpatterns = [
    path("fitting/evaluate/", views.EvaluateView.as_view(), name="fit-evaluate"),
    path("fitting/sessions/", views.SessionListCreateView.as_view(), name="sessions"),
    path("fitting/sessions/<uuid:pk>/", views.SessionDetailView.as_view(), name="session-detail"),
    path("fitting/sessions/<uuid:pk>/items/", views.SessionItemsView.as_view(), name="session-items"),
    path("fitting/sessions/<uuid:pk>/items/<int:item_id>/", views.SessionItemDetailView.as_view(), name="session-item"),
]