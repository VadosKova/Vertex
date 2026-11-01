from rest_framework import serializers

from .measurements import (AGE_RANGE, HEIGHT_RANGE, REQUIRED, WEIGHT_RANGE, validate_bmi, validate_measurements)
from .models import Avatar


class AvatarSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=60, required=False)
    gender = serializers.ChoiceField(choices=Avatar.Gender.choices, required=False)
    estimated_fields = serializers.SerializerMethodField()

    class Meta:
        model = Avatar
        fields = ("id", "name", "gender", "age", "height_cm", "weight_kg", "body_type", "measurements",
                  "estimated_fields", "measurements_updated_at", "is_default", "created_at")
        read_only_fields = ("id", "measurements_updated_at", "is_default", "created_at")

    def get_estimated_fields(self, obj):
        return obj.full_measurements()[1]

    def validate_name(self, value):
        value = " ".join(value.split())
        if not value:
            raise serializers.ValidationError("Name cannot be empty")
        return value