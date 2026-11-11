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


def _validate_sizes(raw_sizes, where, errors):
    entries, seen = [], set()
    if not isinstance(raw_sizes, list) or not raw_sizes:
        errors.append(f"{where}: 'sizes' must be a non-empty list.")
        return entries
    for order, raw in enumerate(raw_sizes):
        w = f"{where}, size #{order + 1}"
        if not isinstance(raw, dict):
            errors.append(f"{w}: must be an object.")
            continue
        label = raw.get("label")
        if not isinstance(label, str) or not label.strip() or len(label.strip()) > 10:
            errors.append(f"{w}: 'label' must be a non-empty text up to 10 characters.")
            continue
        label = label.strip()
        w = f"{where}, size {label}"
        if label.upper() in seen:
            errors.append(f"{w}: duplicate size label.")
            continue
        seen.add(label.upper())
        entry, ok = {"label": label, "order": order}, True
        for key in raw:
            if key != "label" and key not in ZONES:
                errors.append(f"{w}: unknown zone '{key}' (allowed: {', '.join(ZONES)}).")
                ok = False
        for zone, measure in ZONES.items():
            if zone not in raw:
                continue
            rng = raw[zone]
            if not (isinstance(rng, list) and len(rng) == 2 and all(_number(x) for x in rng)):
                errors.append(f"{w}: '{zone}' must be [min, max] in cm.")
                ok = False
                continue
            lo, hi = rng
            if lo > hi:
                errors.append(f"{w}: '{zone}' has min greater than max.")
                ok = False
                continue
            lim_lo, lim_hi = SPEC[measure][1], SPEC[measure][2]
            if lo < lim_lo or hi > lim_hi:
                errors.append(f"{w}: '{zone}' must stay within {lim_lo}-{lim_hi} cm.")
                ok = False
                continue
            entry[f"{zone}_min"], entry[f"{zone}_max"] = float(lo), float(hi)
        if ok and len(entry) == 2:
            errors.append(f"{w}: at least one zone ({', '.join(ZONES)}) is required.")
            ok = False
        if ok:
            entries.append(entry)
    return entries