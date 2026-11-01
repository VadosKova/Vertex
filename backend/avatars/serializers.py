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

    def validate_height_cm(self, v):
        if not HEIGHT_RANGE[0] <= v <= HEIGHT_RANGE[1]:
            raise serializers.ValidationError(f"Must be between {HEIGHT_RANGE[0]} and {HEIGHT_RANGE[1]} cm.")
        return v

    def validate_weight_kg(self, v):
        if not WEIGHT_RANGE[0] <= v <= WEIGHT_RANGE[1]:
            raise serializers.ValidationError(f"Must be between {WEIGHT_RANGE[0]} and {WEIGHT_RANGE[1]} kg.")
        return v

    def validate_age(self, v):
        if not AGE_RANGE[0] <= v <= AGE_RANGE[1]:
            raise serializers.ValidationError(f"Must be between {AGE_RANGE[0]} and {AGE_RANGE[1]}.")
        return v

    def validate_measurements(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object.")
        errors = validate_measurements(value)
        if errors:
            raise serializers.ValidationError(errors)
        return value