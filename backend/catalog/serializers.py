from rest_framework import serializers

from fitting.engine import recommend_size

from .models import Category, Product, ProductSize, ZONES


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ("slug", "name_uk", "name_en")