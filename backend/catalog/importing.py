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


def load_file(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise CatalogDataError([f"File not found: {path}"])
    except UnicodeDecodeError:
        raise CatalogDataError(["The file must be saved as UTF-8."])
    except json.JSONDecodeError as exc:
        raise CatalogDataError([f"Invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"])


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)