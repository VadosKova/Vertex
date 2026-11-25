from decimal import Decimal
from types import SimpleNamespace
from urllib.parse import urlparse

from django.core import signing
from django.db import IntegrityError, transaction

from fitting.engine import recommend_size

from .default_charts import default_chart
from .importers import PageImportError, guess_category_slug, parse_product_page
from .models import Brand, Category, Product, ProductSize
from .shops import shop_for

TOKEN_SALT = "vertex.import-preview"
TOKEN_TTL = 30 * 60
MAX_SIZES = 40


class NeedsCategory(Exception):


class _Sizes(list):
    def all(self):
        return self


def _preview_product(entries, stretch):
    return SimpleNamespace(fabric_stretch=stretch,
                           sizes=_Sizes(ProductSize(**{k: v for k, v in e.items()}) for e in entries))


def _entries_from_product(product):
    out = []
    for size in product.sizes.all():
        entry = {"label": size.label, "order": size.order}
        for zone in ("chest", "waist", "hips", "shoulders", "inseam", "sleeve"):
            lo, hi = getattr(size, f"{zone}_min"), getattr(size, f"{zone}_max")
            if lo is not None and hi is not None:
                entry[f"{zone}_min"], entry[f"{zone}_max"] = lo, hi
        out.append(entry)
    return out


def _from_product(product, source):
    return {"url": product.source_url, "title": product.title, "brand": product.brand.name,
            "image_url": product.image_url, "price": float(product.price) if product.price is not None else None,
            "currency": product.currency, "category": product.category.slug, "gender": product.gender,
            "source": source, "sizes": _entries_from_product(product), "stretch": product.fabric_stretch,
            "product_id": product.pk, "created": False}


def build_preview(user, url, fetch, category=None, gender=None):
    existing = (Product.objects.filter(owner=user, source_url=url).select_related("brand", "category")
                .prefetch_related("sizes").first())
    if existing:
        data = _from_product(existing, "existing")
        data["shop"] = shop_for(url)
        return data

    parsed = parse_product_page(fetch(url), url)
    slug = category or guess_category_slug(parsed["title"]) or guess_category_slug(urlparse(url).path)
    cat = Category.objects.filter(slug=slug).first() if slug else None
    gender = gender or "unisex"
    base = {"url": url, "shop": shop_for(url), "title": parsed["title"], "brand": parsed["brand"],
            "image_url": parsed["image_url"], "currency": parsed["currency"], "product_id": None, "created": False,
            "price": float(parsed["price"]) if parsed["price"] is not None else None, "stretch": 0.03}

    if parsed["sizes"]:
        return {**base, "category": cat.slug if cat else None, "gender": gender, "source": "brand",
                "sizes": parsed["sizes"][:MAX_SIZES]}

    for tpl in (Product.objects.filter(is_template=True, brand__name__iexact=parsed["brand"])
                .select_related("brand", "category").prefetch_related("sizes")):
        if tpl.title.lower() in parsed["title"].lower():
            data = _from_product(tpl, "template")
            return {**base, **{k: data[k] for k in ("category", "gender", "sizes", "stretch", "product_id")},
                    "source": "template"}
    entries = default_chart(slug, gender) if cat else None
    if entries is None:
        raise PageImportError("size_chart_not_found", "Could not find a size chart on the page.")
    return {**base, "category": cat.slug, "gender": gender, "source": "default", "sizes": entries}


def public_preview(data, measurements=None):
    sizes = [{"label": e["label"], "ranges": {z: [e[f"{z}_min"], e[f"{z}_max"]]
                                              for z in ("chest", "waist", "hips", "shoulders", "inseam", "sleeve")
                                              if f"{z}_min" in e}} for e in data["sizes"]]
    labels = [s["label"] for s in sorted(data["sizes"], key=lambda e: e["order"])]
    rec = recommend_size(_preview_product(data["sizes"], data.get("stretch", 0.03)), measurements) if measurements else None
    return {"url": data["url"], "shop": data["shop"], "title": data["title"], "brand": data["brand"],
            "image_url": data["image_url"], "price": data["price"], "currency": data["currency"],
            "category": data["category"], "needs_category": data["category"] is None, "gender": data["gender"],
            "size_chart_source": data["source"] if data["source"] != "template" else "brand",
            "source": data["source"], "approximate": data["source"] == "default",
            "size_range": f"{labels[0]}–{labels[-1]}" if len(labels) > 1 else labels[0], "sizes": sizes,
            "recommended_size": rec["label"] if rec else None, "compatibility": rec["compatibility"] if rec else None,
            "product_id": data.get("product_id"), "already_in_catalog": data.get("product_id") is not None}


def make_token(user, data):
    return signing.dumps({"u": user.pk, "d": data}, salt=TOKEN_SALT, compress=True)


def read_token(user, token):
    payload = signing.loads(token, salt=TOKEN_SALT, max_age=TOKEN_TTL)
    if payload.get("u") != user.pk:
        raise signing.BadSignature("foreign token")
    return payload["d"]


@transaction.atomic
def create_from_preview(user, data, category=None, gender=None):
    if data.get("product_id"):
        product = Product.objects.get(pk=data["product_id"])
        return product, False
    slug = category or data["category"]
    cat = Category.objects.filter(slug=slug).first() if slug else None
    if cat is None:
        raise NeedsCategory()
    brand = Brand.objects.filter(name__iexact=data["brand"]).first() or Brand.objects.create(name=data["brand"])
    try:
        with transaction.atomic():
            product = Product.objects.create(
                brand=brand, category=cat, title=data["title"], image_url=data["image_url"], source_url=data["url"],
                owner=user, gender=gender or data["gender"],
                size_chart_source="default" if data["source"] == "default" else "brand",
                price=Decimal(str(data["price"])) if data["price"] is not None else None, currency=data["currency"])
    except IntegrityError:
        return Product.objects.get(owner=user, source_url=data["url"]), False
    ProductSize.objects.bulk_create([ProductSize(product=product, **e) for e in data["sizes"]])
    return product, True