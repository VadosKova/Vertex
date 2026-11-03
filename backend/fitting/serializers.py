from rest_framework import serializers

from .models import TryOnItem


class EvaluateRequestSerializer(serializers.Serializer):
    avatar_id = serializers.UUIDField(required=False)
    product_id = serializers.IntegerField()
    size = serializers.CharField(required=False, max_length=10)
    lang = serializers.ChoiceField(choices=["uk", "en"], required=False)


class SessionCreateSerializer(serializers.Serializer):
    avatar_id = serializers.UUIDField(required=False)


class ItemCreateSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    size = serializers.CharField(required=False, max_length=10)