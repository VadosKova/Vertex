from rest_framework import serializers

from fitting.engine import recommend_size

from .models import Category, Product, ProductSize, ZONES

ORDERINGS = ("compat", "new", "price_asc", "price_desc")


class CategorySerializer(serializers.ModelSerializer):
    count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Category
        fields = ("slug", "name_uk", "name_en", "count")


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
    price = serializers.SerializerMethodField()
    old_price = serializers.SerializerMethodField()
    discount_percent = serializers.SerializerMethodField()
    recommended_size = serializers.SerializerMethodField()
    compatibility = serializers.SerializerMethodField()
    approximate = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ("id", "title", "brand", "category", "gender", "image_url", "garment_model_url", "source_url",
                  "is_template", "size_chart_source", "approximate", "price", "old_price", "currency",
                  "discount_percent", "fit_type", "sizes", "recommended_size", "compatibility")

    def get_price(self, obj):
        return float(obj.price) if obj.price is not None else None

    def get_old_price(self, obj):
        return float(obj.old_price) if obj.old_price is not None else None

    def get_discount_percent(self, obj):
        if obj.price is None or obj.old_price is None or obj.old_price <= obj.price:
            return None
        return int(round((obj.old_price - obj.price) / obj.old_price * 100))

    def get_approximate(self, obj):
        return obj.size_chart_source == "default"

    def _recommendation(self, obj):
        cache = self.context.get("compat_map")
        if cache is not None and obj.pk in cache:
            return cache[obj.pk]
        measurements = self.context.get("measurements")
        if not measurements:
            return None, None
        rec = recommend_size(obj, measurements)
        return (rec["label"], rec["compatibility"]) if rec else (None, None)

    def get_recommended_size(self, obj):
        return self._recommendation(obj)[0]

    def get_compatibility(self, obj):
        return self._recommendation(obj)[1]


class ImportRequestSerializer(serializers.Serializer):
    url = serializers.URLField(max_length=500)
    category = serializers.SlugField(required=False)
    gender = serializers.ChoiceField(choices=Product.Gender.choices, required=False)


class CommaListField(serializers.Field):

    def __init__(self, child, max_items=12, **kwargs):
        super().__init__(**kwargs)
        self.child, self.max_items = child, max_items

    def to_internal_value(self, data):
        items = [x.strip() for x in str(data).split(",") if x.strip()]
        if len(items) > self.max_items:
            raise serializers.ValidationError(f"At most {self.max_items} values.")
        return [self.child.run_validation(x) for x in items]

    def to_representation(self, value):
        return ",".join(value)


class CatalogQuerySerializer(serializers.Serializer):
    category = serializers.SlugField(required=False)
    brand = serializers.CharField(required=False, max_length=80)
    q = serializers.CharField(required=False, max_length=100)
    personalized = serializers.BooleanField(required=False, default=True)
    avatar = serializers.UUIDField(required=False)
    gender = CommaListField(serializers.ChoiceField(choices=Product.Gender.choices), required=False)
    sizes = CommaListField(serializers.CharField(max_length=10), required=False)
    fit = CommaListField(serializers.ChoiceField(choices=["slim", "regular", "loose"]), required=False)
    min_compat = serializers.IntegerField(required=False, min_value=0, max_value=100)
    min_price = serializers.DecimalField(required=False, max_digits=10, decimal_places=2, min_value=0)
    max_price = serializers.DecimalField(required=False, max_digits=10, decimal_places=2, min_value=0)
    ordering = serializers.ChoiceField(required=False, choices=ORDERINGS)

    def validate(self, attrs):
        lo, hi = attrs.get("min_price"), attrs.get("max_price")
        if lo is not None and hi is not None and lo > hi:
            raise serializers.ValidationError({"min_price": "Must not exceed max_price."})
        return attrs