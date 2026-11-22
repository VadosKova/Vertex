from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/token/", views.LoginView.as_view(), name="token"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/google/", views.GoogleLoginView.as_view(), name="google-login"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset/verify/", views.PasswordResetVerifyView.as_view(), name="password-reset-verify"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
]