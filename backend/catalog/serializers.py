from rest_framework import serializers

from fitting.engine import recommend_size

from .models import Category, Product, ProductSize, ZONES


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("slug", "name_uk", "name_en")


class ProductSizeSerializer(serializers.ModelSerializer):
    ranges = serializers.SerializerMethodField()

    class Meta:
        model = ProductSize
        fields = ("label", "ranges")

    def get_ranges(self, obj):
        return {z: r for z in ZONES if (r := obj.range(z))}