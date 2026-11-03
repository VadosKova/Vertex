from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from avatars.models import Avatar
from fitting.engine import evaluate_product

from .filtering import fitting_products
from .importers import PageImportError, assert_public_url, fetch_html, parse_product_page, parse_range
from .models import Brand, Category, Product, ProductSize

PASSWORD = "S3cure-pass-word"
BODY = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}
DEFAULT_CHART = {"S": ((88, 92), (74, 78), (92, 96)), "M": ((92, 100), (78, 86), (96, 102)),
                 "L": ((100, 108), (86, 94), (102, 110))}


class CatalogBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice", gender="male")
        self.other = User.objects.create_user("bob@example.com", PASSWORD, username="Bob", gender="male")
        self.client.force_authenticate(self.user)

    def make_avatar(self, user=None, **over):
        base = dict(user=user or self.user, name="Me", gender="male", age=25, height_cm=180, weight_kg=75,
                    measurements=dict(BODY), is_default=True)
        base.update(over)
        return Avatar.objects.create(**base)

    def make_product(self, owner=None, stretch=0.03, gender="unisex", title="Tee", chart=None, slug="tshirts"):
        cat, _ = Category.objects.get_or_create(slug=slug, defaults={"name_uk": slug, "name_en": slug})
        brand, _ = Brand.objects.get_or_create(name="Brandy")
        p = Product.objects.create(brand=brand, category=cat, title=title, gender=gender, owner=owner,
                                   fabric_stretch=stretch)
        for i, (label, (c, w, h)) in enumerate((chart or DEFAULT_CHART).items()):
            ProductSize.objects.create(product=p, label=label, order=i, chest_min=c[0], chest_max=c[1],
                                       waist_min=w[0], waist_max=w[1], hips_min=h[0], hips_max=h[1])
        return p


# --importer--
PAGE = """
<html><head><title>Fallback</title>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Product",
 "name":"Slim Fit Jeans","brand":{"@type":"Brand","name":"DenimCo"},"image":["https://cdn.example/jeans.jpg"]}]}</script>
</head><body><table>
<tr><th>Розмір</th><th>Обхват талії (см)</th><th>Обхват стегон (см)</th></tr>
<tr><td>30</td><td>74-79</td><td>92–97</td></tr>
<tr><td>32</td><td>79-85</td><td>97-102</td></tr>
</table></body></html>
"""
PAGE_INCHES = """<script type="application/ld+json">{"@type":"Product","name":"Classic Tee","brand":"Acme"}</script>
<table><tr><th>Size</th><th>Chest (in)</th></tr><tr><td>m</td><td>36-38</td></tr></table>"""


class ParserTests(CatalogBase):
    def test_parse_range_variants(self):
        self.assertEqual(parse_range("92-96"), (92.0, 96.0))
        self.assertEqual(parse_range("92 – 96 см"), (92.0, 96.0))
        self.assertEqual(parse_range("88,5-92"), (88.5, 92.0))
        self.assertEqual(parse_range("90"), (88.0, 92.0))
        self.assertIsNone(parse_range("n/a"))
        self.assertAlmostEqual(parse_range("36-38", inches=True)[0], 91.44, places=2)

    def test_parse_jsonld_and_ukrainian_table(self):
        out = parse_product_page(PAGE)
        self.assertEqual((out["title"], out["brand"]), ("Slim Fit Jeans", "DenimCo"))
        self.assertEqual(out["image_url"], "https://cdn.example/jeans.jpg")
        self.assertEqual([s["label"] for s in out["sizes"]], ["30", "32"])
        self.assertEqual((out["sizes"][0]["waist_min"], out["sizes"][0]["hips_max"]), (74.0, 97.0))

    def test_inches_are_converted(self):
        out = parse_product_page(PAGE_INCHES)
        self.assertEqual(out["sizes"][0]["label"], "M")
        self.assertAlmostEqual(out["sizes"][0]["chest_min"], 91.4, places=1)

    def test_page_without_table_has_no_sizes(self):
        self.assertEqual(parse_product_page("<html><title>x</title></html>")["sizes"], [])


class SsrfTests(CatalogBase):
    def test_blocks_non_http_and_private_targets(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x", "http://127.0.0.1/admin",
                    "http://localhost:8000/", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/"):
            with self.assertRaises(PageImportError, msg=url):
                assert_public_url(url)

    def test_redirect_to_a_private_address_is_blocked(self):
        resp = mock.Mock(is_redirect=True, headers={"Location": "http://127.0.0.1/secret"}, status_code=302)

        def fake_dns(host, port):
            ip = host if host.replace(".", "").isdigit() else "93.184.216.34"
            return [(2, 1, 6, "", (ip, port))]

        with mock.patch("catalog.importers.socket.getaddrinfo", side_effect=fake_dns), \
                mock.patch("catalog.importers.requests.get", return_value=resp):
            with self.assertRaises(PageImportError) as ctx:
                fetch_html("https://shop.example/item")
        self.assertEqual(ctx.exception.code, "forbidden_host")


class ImportEndpointTests(CatalogBase):
    def setUp(self):
        super().setUp()
        Category.objects.create(slug="jeans", name_uk="Джинси", name_en="Jeans")
        self.url = reverse("product-import")

    def test_import_creates_a_private_product_with_sizes(self):
        with mock.patch("catalog.views.fetch_html", return_value=PAGE):
            r = self.client.post(self.url, {"url": "https://shop.example/jeans"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["category"], r.data["brand"]), ("jeans", "DenimCo"))
        self.assertEqual(len(r.data["sizes"]), 2)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("product-detail", args=[r.data["id"]])).status_code, 404)

    def test_same_url_twice_is_idempotent(self):
        with mock.patch("catalog.views.fetch_html", return_value=PAGE) as fh:
            a = self.client.post(self.url, {"url": "https://shop.example/jeans"}, format="json")
            b = self.client.post(self.url, {"url": "https://shop.example/jeans"}, format="json")
        self.assertEqual((a.data["id"], b.status_code), (b.data["id"], 200))
        self.assertEqual(fh.call_count, 1)

    def test_falls_back_to_the_template_db_when_no_size_chart(self):
        tpl = self.make_product(title="Slim Fit Jeans", slug="jeans")
        Brand.objects.filter(pk=tpl.brand_id).update(name="DenimCo")
        Product.objects.filter(pk=tpl.pk).update(is_template=True)
        page = PAGE.replace("<table>", "<div>").replace("</table>", "</div>")
        with mock.patch("catalog.views.fetch_html", return_value=page):
            r = self.client.post(self.url, {"url": "https://shop.example/blocked"}, format="json")
        self.assertEqual((r.status_code, r.data["id"]), (200, tpl.pk))

    def test_unknown_page_gives_422_with_a_code(self):
        with mock.patch("catalog.views.fetch_html", return_value="<html><title>Shop</title></html>"):
            r = self.client.post(self.url, {"url": "https://shop.example/x"}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (422, "size_chart_not_found"))

    def test_fetch_errors_and_bad_input(self):
        r = self.client.post(self.url, {"url": "http://127.0.0.1/x"}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (422, "forbidden_host"))
        self.assertEqual(self.client.post(self.url, {"url": "not-a-url"}, format="json").status_code, 400)

    def test_unknown_category_requires_an_explicit_choice(self):
        html = PAGE.replace("Slim Fit Jeans", "Mystery Garment")
        with mock.patch("catalog.views.fetch_html", return_value=html):
            r = self.client.post(self.url, {"url": "https://shop.example/m"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("category", r.data)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(self.url, {"url": "https://shop.example/x"}, format="json").status_code, 401)


# --catalog list--
class CatalogListTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.avatar = self.make_avatar()
        self.fits = self.make_product(title="Fits Tee")
        self.too_big = self.make_product(title="Giant Tee", chart={"XXL": ((130, 140), (120, 130), (130, 140))})
        self.female = self.make_product(title="Her Tee", gender="female")
        self.hoodie = self.make_product(title="Fits Hoodie", slug="hoodies")
        self.mine = self.make_product(title="My import", owner=self.user)
        self.theirs = self.make_product(title="Their import", owner=self.other)

    def titles(self, **params):
        r = self.client.get(reverse("products"), params)
        self.assertEqual(r.status_code, 200, r.data)
        return {p["title"] for p in r.data["results"]}

    def test_default_list_is_personalised(self):
        self.assertEqual(self.titles(), {"Fits Tee", "Fits Hoodie", "My import"})

    def test_personalisation_can_be_switched_off_but_privacy_holds(self):
        t = self.titles(personalized="false")
        self.assertIn("Giant Tee", t)
        self.assertIn("Her Tee", t)
        self.assertNotIn("Their import", t)

    def test_category_search_and_brand_filters(self):
        self.assertEqual(self.titles(category="hoodies"), {"Fits Hoodie"})
        self.assertEqual(self.titles(q="hoodie"), {"Fits Hoodie"})
        self.assertEqual(self.titles(brand="brandy", category="tshirts"), {"Fits Tee", "My import"})

    def test_card_has_brand_and_recommended_size(self):
        card = self.client.get(reverse("products"), {"category": "hoodies"}).data["results"][0]
        self.assertEqual((card["brand"], card["recommended_size"]), ("Brandy", "M"))

    def test_another_avatar_changes_the_result(self):
        plus = self.make_avatar(name="Plus", is_default=False, measurements={
            "chest_circumference": 135, "waist_circumference": 125, "hip_circumference": 135})
        r = self.client.get(reverse("products"), {"avatar": str(plus.pk)})
        self.assertEqual({p["title"] for p in r.data["results"]}, {"Giant Tee"})

    def test_foreign_or_malformed_avatar_param_neither_leaks_nor_crashes(self):
        foreign = self.make_avatar(user=self.other, is_default=False)
        self.assertEqual(self.client.get(reverse("products"), {"avatar": str(foreign.pk)}).status_code, 200)
        self.assertEqual(self.client.get(reverse("products"), {"avatar": "garbage"}).status_code, 200)

    def test_without_an_avatar_everything_visible_is_shown(self):
        self.avatar.delete()
        self.assertIn("Giant Tee", self.titles())

    def test_query_count_does_not_grow_with_the_catalog(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("products"))
            return len(ctx)
        base = count()
        for i in range(15):
            self.make_product(title=f"Extra {i}")
        self.assertLessEqual(count(), base + 1)

    def test_categories_and_detail(self):
        r = self.client.get(reverse("categories"))
        self.assertEqual({c["slug"] for c in r.data}, {"tshirts", "hoodies"})
        d = self.client.get(reverse("product-detail", args=[self.fits.pk]))
        self.assertEqual(list(d.data["sizes"][0]["ranges"]["chest"]), [88.0, 92.0])

    def test_pagination(self):
        for i in range(25):
            self.make_product(title=f"Bulk {i}")
        r = self.client.get(reverse("products"), {"personalized": "false"})
        self.assertEqual((len(r.data["results"]), r.data["count"] > 25), (20, True))
        self.assertIsNotNone(r.data["next"])
        r2 = self.client.get(reverse("products"), {"personalized": "false", "page_size": 5, "page": 2})
        self.assertEqual(len(r2.data["results"]), 5)
        self.assertEqual(self.client.get(reverse("products"), {"page_size": 1000}).status_code, 200)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("products")).status_code, 401)


class SqlFilterMatchesEngineTests(CatalogBase):
    def test_consistency_over_a_grid(self):
        products = [self.make_product(title="A", stretch=0.03),
                    self.make_product(title="B", stretch=0.0, chart={"S": ((80, 84), (66, 70), (86, 90))}),
                    self.make_product(title="C", stretch=0.08, chart={"XL": ((110, 120), (96, 106), (112, 122))})]
        checked = 0
        for chest in (78, 85, 93, 99, 104, 112, 125):
            for waist in (62, 70, 80, 90, 100, 115):
                for hips in (85, 95, 105, 118, 130):
                    m = {"chest_circumference": chest, "waist_circumference": waist, "hip_circumference": hips}
                    sql = set(fitting_products(Product.objects.all(), m).values_list("pk", flat=True))
                    for p in products:
                        p = Product.objects.prefetch_related("sizes").get(pk=p.pk)
                        py = any(r["fits"] for r in evaluate_product(p, m))
                        self.assertEqual(p.pk in sql, py, f"mismatch {p.title} {m}")
                        checked += 1
        self.assertEqual(checked, 7 * 6 * 5 * 3)


class SeedCommandTests(CatalogBase):
    def test_seed_is_idempotent_and_usable(self):
        call_command("seed_catalog", verbosity=0)
        call_command("seed_catalog", verbosity=0)
        self.assertEqual(Category.objects.count(), 4)
        self.assertEqual(Product.objects.filter(is_template=True).count(), 4)
        self.assertEqual(ProductSize.objects.filter(product__title="Basic Tee").count(), 4)
        self.make_avatar()
        r = self.client.get(reverse("products"))
        self.assertGreaterEqual(len(r.data["results"]), 1)
        self.assertNotIn("Wrap Dress", {p["title"] for p in r.data["results"]})