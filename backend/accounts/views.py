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


class RegisterView(generics.CreateAPIView):
    serializer_class = s.RegisterSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"


class LoginView(TokenObtainPairView):
    serializer_class = s.EmailTokenObtainPairSerializer
    throttle_scope = "auth"


class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.UserSettingsSerializer

    def get_object(self):
        return self.request.user

    def perform_destroy(self, instance):
        instance.delete()


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    def post(self, request):
        ser = s.PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=ser.validated_data["email"], is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = settings.PASSWORD_RESET_LINK.format(uid=uid, token=token)
            subject, body = RESET_TEXT.get(user.language, RESET_TEXT["uk"])
            send_mail(subject, body.format(link=link), settings.DEFAULT_FROM_EMAIL, [user.email])
        return Response({"detail": "If the account exists, an email has been sent."})


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    def post(self, request):
        ser = s.PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = User.objects.get(pk=urlsafe_base64_decode(ser.validated_data["uid"]).decode())
        except (User.DoesNotExist, ValueError, TypeError, OverflowError, UnicodeDecodeError):
            user = None
        if user is None or not default_token_generator.check_token(user, ser.validated_data["token"]):
            return Response({"detail": "Invalid or expired token."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated."})