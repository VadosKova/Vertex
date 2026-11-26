from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .passwords import validate_password_strength

User = get_user_model()


def clean_username(value):
    value = " ".join(value.split())
    if len(value) < 2:
        raise serializers.ValidationError("Username must be at least 2 characters.")
    if any(ord(ch) < 32 for ch in value):
        raise serializers.ValidationError("Username contains invalid characters.")
    return value


class UserSettingsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(max_length=30)
    reminder_day = serializers.IntegerField(min_value=1, max_value=28, required=False)
    reminder_time = serializers.TimeField(format="%H:%M", input_formats=["%H:%M", "%H:%M:%S"], required=False)
    timezone = serializers.CharField(source="timezone_name", max_length=64, required=False)

    class Meta:
        model = User
        fields = ("id", "email", "username", "gender", "language", "theme", "reminder_enabled", "reminder_day",
                  "reminder_time", "timezone", "push_enabled", "in_app_enabled")
        read_only_fields = ("id", "email")

    def validate_timezone(self, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise serializers.ValidationError("Unknown time zone (use an IANA name such as Europe/Kyiv).")
        return value

    def validate_username(self, value):
        return clean_username(value)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    username = serializers.CharField(max_length=30)
    gender = serializers.ChoiceField(choices=User.Gender.choices)

    class Meta:
        model = User
        fields = ("email", "username", "gender", "password", "language")
        extra_kwargs = {"language": {"required": False}}

    def validate_username(self, value):
        return clean_username(value)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_password(self, value):
        return validate_password_strength(value)

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(instance)
        return {
            "user": UserSettingsSerializer(instance).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    remember_me = serializers.BooleanField(required=False, default=True)

    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        remember = attrs.pop("remember_me", True)
        super(TokenObtainPairSerializer, self).validate(attrs)
        refresh = self.get_token(self.user)
        days = getattr(settings, "REFRESH_REMEMBER_DAYS", 30) if remember else getattr(settings, "REFRESH_SESSION_DAYS", 1)
        refresh.set_exp(lifetime=timedelta(days=days))
        return {"refresh": str(refresh), "access": str(refresh.access_token),
                "user": UserSettingsSerializer(self.user).data}


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=20)


class PasswordResetConfirmSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, max_length=200)
    new_password_confirm = serializers.CharField(write_only=True, required=False, max_length=200)

    def validate(self, attrs):
        confirm = attrs.get("new_password_confirm")
        if confirm is not None and confirm != attrs["new_password"]:
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    device_token = serializers.CharField(required=False, allow_blank=True, max_length=4096)


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    username = serializers.CharField(max_length=30, required=False)
    gender = serializers.ChoiceField(choices=User.Gender.choices, required=False)

    def validate_username(self, value):
        return clean_username(value)