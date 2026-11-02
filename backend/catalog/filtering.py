from django.db.models import Exists, ExpressionWrapper, F, FloatField, OuterRef, Q

from .models import ProductSize, ZONES

LOOSE_LIMIT_CM = 6.0


def fitting_products(queryset, measurements: dict):
    sizes = ProductSize.objects.filter(product=OuterRef("pk"))
    for zone, key in ZONES.items():
        value = measurements.get(key)
        if value is None:
            continue
        cap = f"{zone}_cap"
        sizes = sizes.annotate(**{cap: ExpressionWrapper(
            F(f"{zone}_max") * (1 + F("product__fabric_stretch")), output_field=FloatField())})
        sizes = sizes.filter(
            Q(**{f"{zone}_min__isnull": True}) | Q(**{f"{zone}_max__isnull": True})
            | (Q(**{f"{cap}__gte": value}) & Q(**{f"{zone}_min__lte": value + LOOSE_LIMIT_CM}))
        )
    return queryset.filter(Exists(sizes))