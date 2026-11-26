from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView

from . import reset
from . import serializers as s
from .passwords import validate_password_strength
from .google import GoogleNotConfigured, InvalidGoogleToken, sign_in_with_google, verify_google_token
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

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


class _AuthFlowView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"


class PasswordResetRequestView(_AuthFlowView):
    def post(self, request):
        ser = s.PasswordResetRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            data = reset.request_code(ser.validated_data["email"])
        except reset.Throttled as exc:
            resp = Response({"code": "too_many_requests", "detail": "Please wait before requesting a new code.",
                             "retry_after": exc.wait}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            resp["Retry-After"] = str(exc.wait)
            return resp
        return Response({"detail": "If the account exists, a code has been sent.", **data})


class PasswordResetVerifyView(_AuthFlowView):
    def post(self, request):
        ser = s.PasswordResetVerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            token = reset.verify_code(ser.validated_data["email"], ser.validated_data["code"].strip())
        except reset.InvalidCode:
            return Response({"code": "invalid_code", "detail": "Invalid or expired code."}, status=400)
        return Response({"reset_token": token, "expires_in": reset.TOKEN_TTL})


class PasswordResetConfirmView(_AuthFlowView):
    def post(self, request):
        ser = s.PasswordResetConfirmSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user, row = reset.consume_token(ser.validated_data["reset_token"])
        except reset.InvalidToken:
            return Response({"code": "invalid_token", "detail": "The reset session is invalid or has expired."},
                            status=400)
        new_password = ser.validated_data["new_password"]
        try:
            validate_password_strength(new_password, user)
        except serializers.ValidationError as exc:
            return Response({"new_password": exc.detail}, status=400)
        if user.check_password(new_password):
            return Response({"new_password": ["The new password must differ from the current one."]}, status=400)
        user.set_password(new_password)
        user.save(update_fields=["password"])
        reset.finish(user, row)
        return Response({"detail": "Password updated."})


class LogoutView(APIView):
    def post(self, request):
        ser = s.LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            token = RefreshToken(ser.validated_data["refresh"])
            if str(token.get("user_id")) == str(request.user.pk):
                token.blacklist()
        except TokenError:
            pass
        device = ser.validated_data.get("device_token")
        if device:
            from notifications.models import DeviceToken
            DeviceToken.objects.filter(user=request.user, token=device).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GoogleLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes: list = []
    throttle_scope = "auth"

    def post(self, request):
        ser = s.GoogleLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        try:
            info = verify_google_token(data["id_token"])
        except GoogleNotConfigured:
            return Response({"detail": "Google sign-in is not configured."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except InvalidGoogleToken:
            return Response({"detail": "Invalid Google token."}, status=status.HTTP_401_UNAUTHORIZED)
        if not info.get("email") or not info.get("email_verified"):
            return Response({"detail": "Google account email is not verified."}, status=status.HTTP_401_UNAUTHORIZED)

        user, created = sign_in_with_google(info, username=data.get("username"), gender=data.get("gender"))
        if not user.is_active:
            return Response({"detail": "Account is disabled."}, status=status.HTTP_403_FORBIDDEN)
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": s.UserSettingsSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "created": created,
            "profile_complete": bool(user.gender),
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)