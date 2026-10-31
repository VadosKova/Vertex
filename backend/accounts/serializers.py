from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def clean_username(value):
    value = " ".join(value.split())
    if len(value) < 2:
        raise serializers.ValidationError("Username must be at least 2 characters")
    if any(ord(ch) < 32 for ch in value):
        raise serializers.ValidationError("Username contains invalid characters")
    return value


class UserSettingsSerializer(serializers.ModelSerializer):
    username = serializers.CharField(max_length=30)

    class Meta:
        model = User
        fields = ("id", "email", "username", "gender", "language", "theme", "reminder_enabled")
        read_only_fields = ("id", "email")

    def validate_username(self, value):
        return clean_username(value)