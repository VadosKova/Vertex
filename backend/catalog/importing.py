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


def validate(data, known_categories):
    errors, products = [], []
    if not isinstance(data, dict) or not isinstance(data.get("products"), list) or not data["products"]:
        return [], ["The file must be an object with a non-empty 'products' list."]
    if len(data["products"]) > MAX_PRODUCTS:
        return [], [f"At most {MAX_PRODUCTS} products per file."]
    seen = set()
    for i, raw in enumerate(data["products"]):
        where = f"products[{i}]"
        if not isinstance(raw, dict):
            errors.append(f"{where}: must be an object.")
            continue
        typos = [k for k in raw if k not in PRODUCT_KEYS and not str(k).startswith("_")]
        if typos:
            errors.append(f"{where}: unknown field(s): {', '.join(map(str, typos))}.")
        brand, title = raw.get("brand"), raw.get("title")
        if not isinstance(brand, str) or not brand.strip() or len(brand.strip()) > 80:
            errors.append(f"{where}: 'brand' is required (up to 80 characters).")
            continue
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
            errors.append(f"{where}: 'title' is required (up to 200 characters).")
            continue
        brand, title = brand.strip(), title.strip()
        where = f'products[{i}] "{brand} {title}"'
        if (brand.lower(), title.lower()) in seen:
            errors.append(f"{where}: duplicate of an earlier product in the file.")
            continue
        seen.add((brand.lower(), title.lower()))
        n_before = len(errors)

        category = raw.get("category")
        if category not in known_categories:
            errors.append(f"{where}: unknown category '{category}' (known: {', '.join(sorted(known_categories))}).")
        gender = raw.get("gender", "unisex")
        if gender not in GENDERS:
            errors.append(f"{where}: 'gender' must be one of {', '.join(sorted(GENDERS))}.")
        stretch = raw.get("fabric_stretch", 0.03)
        if not _number(stretch) or not 0 <= stretch <= 0.3:
            errors.append(f"{where}: 'fabric_stretch' must be a number from 0 to 0.3.")
        urls = {}
        for field in ("image_url", "garment_model_url", "source_url"):
            value = raw.get(field, "")
            if value:
                try:
                    if not isinstance(value, str) or len(value) > 500:
                        raise ValidationError("bad")
                    _url_validator(value)
                except ValidationError:
                    errors.append(f"{where}: '{field}' must be an http(s) URL up to 500 characters.")
            urls[field] = value or ""

        entries, source = [], "brand"
        if raw.get("use_default_chart"):
            if "sizes" in raw:
                errors.append(f"{where}: use either 'sizes' or 'use_default_chart', not both.")
            elif len(errors) == n_before:
                entries = default_chart(category, gender)
                source = "default"
                if entries is None:
                    errors.append(f"{where}: no default size chart for {category}/{gender}.")
        elif "sizes" in raw:
            entries = _validate_sizes(raw["sizes"], where, errors)
        else:
            errors.append(f"{where}: provide 'sizes' or set 'use_default_chart': true.")

        if len(errors) == n_before:
            products.append({"brand": brand, "title": title, "category": category, "gender": gender,
                             "fabric_stretch": float(stretch), "sizes": entries, "size_chart_source": source, **urls})
    return products, errors