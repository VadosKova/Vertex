from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, F, Q
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from avatars.models import Avatar

from .filtering import fitting_products
from django.core import signing
from django.shortcuts import get_object_or_404

from .importers import PageImportError, fetch_html, guess_category_slug
from .importflow import (NeedsCategory, build_preview, create_from_preview, make_token, public_preview,
                         read_token)
from .shops import listed_shops
from urllib.parse import urlparse
from .models import Brand, Category, Product, ProductSize
from fitting.engine import recommend_size

from .serializers import (CatalogQuerySerializer, CategorySerializer, ImportRequestSerializer,
                          ProductSerializer, SimilarQuerySerializer)


def resolve_avatar(request, avatar_id=None):
    qs = Avatar.objects.filter(user=request.user)
    if avatar_id:
        avatar = qs.filter(pk=avatar_id).first()
        if avatar is None:
            raise NotFound("Avatar not found.")
        return avatar
    return qs.filter(is_default=True).first()


def visible_products(user):
    return (Product.objects.filter(Q(owner__isnull=True) | Q(owner=user))
            .select_related("brand", "category").prefetch_related("sizes"))


MAX_COMPAT_CANDIDATES = 2000


def parse_query(request):
    ser = CatalogQuerySerializer(data=request.query_params)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


def filtered_products(request, params, with_category=True):
    qs = visible_products(request.user)
    if with_category and params.get("category"):
        qs = qs.filter(category__slug=params["category"])
    if params.get("brand"):
        qs = qs.filter(brand__name__iexact=params["brand"])
    if params.get("q"):
        qs = qs.filter(Q(title__icontains=params["q"]) | Q(brand__name__icontains=params["q"]))
    if params.get("fit"):
        qs = qs.filter(fit_type__in=params["fit"])
    if params.get("sizes"):
        labels = [x.upper() for x in params["sizes"]]
        qs = qs.filter(sizes__label__in=labels + [x.lower() for x in params["sizes"]]).distinct()
    if params.get("min_price") is not None:
        qs = qs.filter(price__gte=params["min_price"])
    if params.get("max_price") is not None:
        qs = qs.filter(price__lte=params["max_price"])
    avatar = resolve_avatar(request, params.get("avatar"))
    if params.get("gender"):
        qs = qs.filter(gender__in=params["gender"])
    elif avatar and params["personalized"]:
        qs = qs.filter(gender__in=[avatar.gender, "unisex"])
    if avatar and params["personalized"]:
        qs = fitting_products(qs, avatar.full_measurements()[0])
    return qs, avatar


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None

    def get_queryset(self):
        return Category.objects.all().order_by("id")

    def list(self, request, *args, **kwargs):
        params = parse_query(request)
        qs, _ = filtered_products(request, params, with_category=False)
        counts = dict(qs.order_by().values_list("category_id").annotate(n=Count("pk", distinct=True)))
        categories = list(self.get_queryset())
        for c in categories:
            c.count = counts.get(c.pk, 0)
        return Response(self.get_serializer(categories, many=True).data)


class CatalogPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = CatalogPagination

    def list(self, request, *args, **kwargs):
        params = parse_query(request)
        qs, avatar = filtered_products(request, params)
        self._measurements = avatar.full_measurements()[0] if avatar else None
        self._compat_map = None
        ordering = params.get("ordering") or ("compat" if self._measurements and params["personalized"] else "new")
        if ordering == "compat" and not self._measurements:
            ordering = "new"
        min_compat = params.get("min_compat")

        if ordering == "compat" or (min_compat and self._measurements):
            rows = []
            for product in qs.order_by("-created_at", "id")[:MAX_COMPAT_CANDIDATES]:
                rec = recommend_size(product, self._measurements) if self._measurements else None
                rows.append((product, rec["label"] if rec else None, rec["compatibility"] if rec else 0))
            if min_compat:
                rows = [r for r in rows if r[2] >= min_compat]
            if ordering == "compat":
                rows.sort(key=lambda r: -r[2])
            elif ordering == "price_asc":
                rows.sort(key=lambda r: (r[0].price is None, r[0].price or 0))
            elif ordering == "price_desc":
                rows.sort(key=lambda r: (r[0].price is None, -(r[0].price or 0)))
            self._compat_map = {p.pk: (label, pct if label else None) for p, label, pct in rows}
            items = [r[0] for r in rows]
        else:
            if ordering == "price_asc":
                qs = qs.order_by(F("price").asc(nulls_last=True), "id")
            elif ordering == "price_desc":
                qs = qs.order_by(F("price").desc(nulls_last=True), "id")
            else:
                qs = qs.order_by("-created_at", "id")
            items = qs
        page = self.paginate_queryset(items)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["measurements"] = getattr(self, "_measurements", None)
        ctx["compat_map"] = getattr(self, "_compat_map", None)
        return ctx


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer

    def get_queryset(self):
        return visible_products(self.request.user)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        params = parse_query(self.request)
        avatar = resolve_avatar(self.request, params.get("avatar"))
        ctx["measurements"] = avatar.full_measurements()[0] if avatar else None
        return ctx


def _import_error(exc, url):
    body = {"code": exc.code, "detail": str(exc)}
    if exc.code not in ("invalid_url", "forbidden_host"):
        body["suggestion"] = "choose_from_catalog"
        slug = guess_category_slug(urlparse(url).path)
        if slug:
            body["category"] = slug
    return Response(body, status=status.HTTP_422_UNPROCESSABLE_ENTITY)


def _measurements(request, avatar_id=None):
    avatar = resolve_avatar(request, avatar_id)
    return avatar.full_measurements()[0] if avatar else None


class ImportShopsView(APIView):
    def get(self, request):
        return Response({"shops": listed_shops()})


class ProductImportPreviewView(APIView):
    throttle_scope = "import"

    def post(self, request):
        ser = ImportRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not d.get("url"):
            return Response({"url": ["This field is required."]}, status=400)
        try:
            data = build_preview(request.user, d["url"], fetch_html, d.get("category"), d.get("gender"))
        except PageImportError as exc:
            return _import_error(exc, d["url"])
        body = public_preview(data, _measurements(request, d.get("avatar")))
        body["preview_token"] = make_token(request.user, data)
        return Response(body)


class ProductImportView(APIView):
    throttle_scope = "import"

    def post(self, request):
        ser = ImportRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if d.get("preview_token"):
            try:
                data = read_token(request.user, d["preview_token"])
            except signing.BadSignature:
                return Response({"code": "invalid_preview", "detail": "The preview expired. Open the link again."},
                                status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                data = build_preview(request.user, d["url"], fetch_html, d.get("category"), d.get("gender"))
            except PageImportError as exc:
                return _import_error(exc, d["url"])
        try:
            product, created = create_from_preview(request.user, data, d.get("category"), d.get("gender"))
        except NeedsCategory:
            return Response({"category": ["Could not detect the category; please pass one."]}, status=400)
        product = visible_products(request.user).get(pk=product.pk)
        measurements = _measurements(request, d.get("avatar"))
        return Response(ProductSerializer(product, context={"measurements": measurements}).data,
                        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SimilarProductsView(APIView):
    def get(self, request, pk):
        product = get_object_or_404(visible_products(request.user), pk=pk)
        ser = SimilarQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        avatar = resolve_avatar(request, d.get("avatar"))
        qs = visible_products(request.user).filter(category=product.category).exclude(pk=product.pk)
        measurements = avatar.full_measurements()[0] if avatar else None
        if avatar and d["personalized"]:
            qs = qs.filter(gender__in=[avatar.gender, "unisex"])
            qs = fitting_products(qs, measurements)
        elif product.gender != "unisex":
            qs = qs.filter(gender__in=[product.gender, "unisex"])
        rows = []
        for item in qs.order_by("-created_at", "id")[:MAX_COMPAT_CANDIDATES]:
            rec = recommend_size(item, measurements) if measurements else None
            rows.append((item, rec["label"] if rec else None, rec["compatibility"] if rec else None))
        rows.sort(key=lambda r: -(r[2] or 0))
        rows = rows[:d["limit"]]
        compat = {p.pk: (label, pct) for p, label, pct in rows}
        context = {"request": request, "measurements": measurements, "compat_map": compat}
        return Response(ProductSerializer([r[0] for r in rows], many=True, context=context).data)