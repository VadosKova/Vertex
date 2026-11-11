import json
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction

from avatars.measurements import SPEC

from .default_charts import default_chart
from .models import Brand, Category, Product, ProductSize, ZONES

MAX_PRODUCTS = 5000
GENDERS = {"male", "female", "unisex"}
PRODUCT_KEYS = {"brand", "title", "category", "gender", "image_url", "garment_model_url", "source_url",
                "fabric_stretch", "sizes", "use_default_chart"}
_url_validator = URLValidator(schemes=["http", "https"])


class CatalogDataError(Exception):
    def __init__(self, errors):
        super().__init__("; ".join(errors[:3]) + (" ..." if len(errors) > 3 else ""))
        self.errors = errors


@dataclass
class ImportReport:
    created: int = 0
    updated: int = 0

    @property
    def total(self):
        return self.created + self.updated