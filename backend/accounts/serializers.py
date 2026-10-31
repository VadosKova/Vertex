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
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(instance)
        return {
            "user": UserSettingsSerializer(instance).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }