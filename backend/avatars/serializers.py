from rest_framework import serializers

from .measurements import (AGE_RANGE, HEIGHT_RANGE, REQUIRED, WEIGHT_RANGE, validate_bmi, validate_measurements)
from .models import Avatar


class AvatarSerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=60, required=False)
    gender = serializers.ChoiceField(choices=Avatar.Gender.choices, required=False)
    estimated_fields = serializers.SerializerMethodField()