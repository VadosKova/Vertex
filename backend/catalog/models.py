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