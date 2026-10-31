from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from . import serializers as s

User = get_user_model()

RESET_TEXT = {
    "uk": ("Відновлення пароля Vertex", "Щоб встановити новий пароль, перейдіть за посиланням:\n{link}"),
    "en": ("Vertex password reset", "To set a new password open this link:\n{link}"),
}