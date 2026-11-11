from django.conf import settings
from django.db import models


ZONES = {
    "chest": "chest_circumference",
    "waist": "waist_circumference",
    "hips": "hip_circumference",
    "shoulders": "shoulder_width",
    "inseam": "inseam",
}


class Brand(models.Model):
    name = models.CharField(max_length=80, unique=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    slug = models.SlugField(unique=True)
    name_uk = models.CharField(max_length=60)
    name_en = models.CharField(max_length=60)

    class Meta:
        verbose_name_plural = "categories"

    def __str__(self):
        return self.slug


class Product(models.Model):
    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"
        UNISEX = "unisex"

    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    title = models.CharField(max_length=200)
    gender = models.CharField(max_length=6, choices=Gender.choices, default=Gender.UNISEX)
    image_url = models.URLField(max_length=500, blank=True)
    garment_model_url = models.URLField(max_length=500, blank=True)
    source_url = models.URLField(max_length=500, blank=True)
    fabric_stretch = models.FloatField(default=0.03)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="imported_products")
    is_template = models.BooleanField(default=False)
    size_chart_source = models.CharField(max_length=7, choices=[("brand", "Brand chart"), ("default", "Generic chart")],
                                         default="brand")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [models.Index(fields=["category", "gender"])]
        constraints = [
            models.UniqueConstraint(fields=["owner", "source_url"], condition=~models.Q(source_url=""),
                                    name="unique_import_per_owner"),
        ]

    def __str__(self):
        return f"{self.brand} {self.title}"


class ProductSize(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sizes")
    label = models.CharField(max_length=10)
    order = models.PositiveSmallIntegerField(default=0)
    chest_min = models.FloatField(null=True, blank=True)
    chest_max = models.FloatField(null=True, blank=True)
    waist_min = models.FloatField(null=True, blank=True)
    waist_max = models.FloatField(null=True, blank=True)
    hips_min = models.FloatField(null=True, blank=True)
    hips_max = models.FloatField(null=True, blank=True)
    shoulders_min = models.FloatField(null=True, blank=True)
    shoulders_max = models.FloatField(null=True, blank=True)
    inseam_min = models.FloatField(null=True, blank=True)
    inseam_max = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["product_id", "order"]
        constraints = [models.UniqueConstraint(fields=["product", "label"], name="unique_size_per_product")]
        indexes = [models.Index(fields=["chest_min", "chest_max"]), models.Index(fields=["waist_min", "waist_max"]),
                   models.Index(fields=["hips_min", "hips_max"])]

    def range(self, zone):
        lo, hi = getattr(self, f"{zone}_min"), getattr(self, f"{zone}_max")
        return None if lo is None or hi is None else (lo, hi)

    def __str__(self):
        return f"{self.product_id}:{self.label}"