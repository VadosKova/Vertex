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
    def validate(self, attrs):
        attrs[self.username_field] = attrs[self.username_field].strip().lower()
        data = super().validate(attrs)
        data["user"] = UserSettingsSerializer(self.user).data
        return data


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


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()
    username = serializers.CharField(max_length=30, required=False)
    gender = serializers.ChoiceField(choices=User.Gender.choices, required=False)

    def validate_username(self, value):
        return clean_username(value)