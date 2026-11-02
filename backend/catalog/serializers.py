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


class ProductSerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source="brand.name")
    category = serializers.CharField(source="category.slug")
    sizes = ProductSizeSerializer(many=True, read_only=True)
    recommended_size = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "title", "brand", "category", "gender", "image_url", "garment_model_url",
                  "source_url", "is_template", "sizes", "recommended_size")

    def get_recommended_size(self, obj):
        measurements = self.context.get("measurements")
        if not measurements:
            return None
        rec = recommend_size(obj, measurements)
        return rec["label"] if rec else None


class ImportRequestSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    category = serializers.SlugField(required=False)
    gender = serializers.ChoiceField(choices=Product.Gender.choices, required=False)