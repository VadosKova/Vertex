import copy
import json
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User
from avatars.models import Avatar

from .default_charts import FAMILY, default_chart
from .importing import CatalogDataError, import_catalog, load_file, validate
from .models import Brand, Category, Product, ProductSize

EXAMPLE = Path(__file__).resolve().parent / "data" / "example_catalog.json"
CATS = {"tshirts": ("Футболки", "T-shirts"), "hoodies": ("Худі", "Hoodies"),
        "jeans": ("Джинси", "Jeans"), "dresses": ("Сукні", "Dresses")}
SIZES = [{"label": "S", "chest": [88, 92], "waist": [74, 78], "hips": [92, 96]},
         {"label": "M", "chest": [92, 100], "waist": [78, 86], "hips": [96, 102]}]


def product(**over):
    base = {"brand": "B", "title": "T", "category": "tshirts", "gender": "male", "sizes": copy.deepcopy(SIZES)}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


class ImportBase(APITestCase):
    def setUp(self):
        cache.clear()
        for slug, (uk, en) in CATS.items():
            Category.objects.get_or_create(slug=slug, defaults={"name_uk": uk, "name_en": en})


class FileImportTests(ImportBase):
    def test_the_example_file_imports_and_is_usable(self):
        report = import_catalog(load_file(EXAMPLE))
        self.assertEqual((report.created, report.updated), (3, 0))
        tee = Product.objects.get(title="Classic Tee")
        self.assertEqual((tee.is_template, tee.owner, tee.size_chart_source, tee.fabric_stretch),
                         (True, None, "brand", 0.05))
        self.assertEqual(tee.sizes.count(), 4)
        jeans = Product.objects.get(title="Slim Jeans")
        self.assertIsNone(jeans.sizes.get(label="32").chest_min)
        dress = Product.objects.get(title="Wrap Dress")
        self.assertEqual((dress.size_chart_source, dress.sizes.count(), dress.gender), ("default", 4, "female"))

        user = User.objects.create_user("a@example.com", "S3cure-pass-word", username="A", gender="male")
        Avatar.objects.create(user=user, name="Me", gender="male", age=25, height_cm=180, weight_kg=75,
                              is_default=True, measurements={"chest_circumference": 96, "waist_circumference": 82,
                                                             "hip_circumference": 100})
        self.client.force_authenticate(user)
        r = self.client.get(reverse("products"))
        cards = {c["title"]: c for c in r.data["results"]}
        self.assertEqual(cards["Classic Tee"]["recommended_size"], "M")
        self.assertFalse(cards["Classic Tee"]["approximate"])
        self.assertNotIn("Wrap Dress", cards)

    def test_reimport_is_idempotent_and_replaces_the_chart(self):
        data = {"products": [product()]}
        self.assertEqual(import_catalog(data).created, 1)
        data["products"][0]["sizes"][1]["chest"] = [93, 101]
        data["products"][0]["fabric_stretch"] = 0.08
        report = import_catalog(data)
        self.assertEqual((report.created, report.updated), (0, 1))
        p = Product.objects.get(title="T")
        self.assertEqual((Product.objects.count(), ProductSize.objects.count(), p.fabric_stretch), (1, 2, 0.08))
        self.assertEqual(p.sizes.get(label="M").chest_min, 93.0)

    def test_matching_ignores_case_and_does_not_touch_users_imports(self):
        owner = User.objects.create_user("o@example.com", "S3cure-pass-word", username="O")
        Brand.objects.create(name="B")
        mine = Product.objects.create(brand=Brand.objects.get(name="B"), title="T", owner=owner,
                                      category=Category.objects.get(slug="tshirts"))
        report = import_catalog({"products": [product(brand="b", title="t")]})
        self.assertEqual(report.created, 1)
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(Brand.objects.count(), 1)
        mine.refresh_from_db()
        self.assertEqual(mine.owner, owner)

    def test_dry_run_writes_nothing(self):
        report = import_catalog({"products": [product()]}, dry_run=True)
        self.assertEqual(report.created, 1)
        self.assertEqual((Product.objects.count(), Brand.objects.count(), ProductSize.objects.count()), (0, 0, 0))

    def test_all_or_nothing_and_every_problem_is_reported(self):
        data = {"products": [product(title="Good"), product(title="Bad1", category="coats"),
                             product(title="Bad2", gender="x"), product(title="Bad3", fabric_stretch=2)]}
        with self.assertRaises(CatalogDataError) as ctx:
            import_catalog(data)
        self.assertEqual(len(ctx.exception.errors), 3)
        self.assertTrue(all(e.startswith("products[") for e in ctx.exception.errors))
        self.assertEqual(Product.objects.count(), 0)


class ValidationTests(ImportBase):
    def problems(self, **over):
        prod = product(**over)
        _, errors = validate({"products": [prod]}, set(CATS))
        return errors

    def test_each_kind_of_invalid_product_is_rejected_with_a_clear_message(self):
        cases = {
            "brand": ({"brand": ""}, "'brand' is required"),
            "title": ({"title": None}, "'title' is required"),
            "category": ({"category": "coats"}, "unknown category 'coats'"),
            "gender": ({"gender": "other"}, "'gender' must be one of"),
            "stretch": ({"fabric_stretch": 0.9}, "'fabric_stretch' must be"),
            "stretch type": ({"fabric_stretch": "a lot"}, "'fabric_stretch' must be"),
            "url": ({"image_url": "ftp://x/y.jpg"}, "'image_url' must be an http(s) URL"),
            "empty sizes": ({"sizes": []}, "'sizes' must be a non-empty list"),
            "no sizes": ({"sizes": None}, "provide 'sizes' or set 'use_default_chart'"),
            "typo": ({"fabric_strech": 0.1}, "unknown field(s): fabric_strech"),
            "both": ({"use_default_chart": True}, "not both"),
            "duplicate label": ({"sizes": SIZES + [{"label": "s", "chest": [100, 104]}]}, "duplicate size label"),
            "bad label": ({"sizes": [{"label": "", "chest": [90, 94]}]}, "'label' must be"),
            "unknown zone": ({"sizes": [{"label": "S", "bust": [90, 94]}]}, "unknown zone 'bust'"),
            "min>max": ({"sizes": [{"label": "S", "chest": [100, 90]}]}, "min greater than max"),
            "out of range": ({"sizes": [{"label": "S", "waist": [10, 20]}]}, "must stay within"),
            "not numbers": ({"sizes": [{"label": "S", "chest": ["a", "b"]}]}, "must be [min, max]"),
            "no zones": ({"sizes": [{"label": "S"}]}, "at least one zone"),
            "default unsupported": ({"use_default_chart": True, "sizes": None, "category": "dresses",
                                     "gender": "male"}, "no default size chart for dresses/male"),
        }
        for name, (over, fragment) in cases.items():
            errors = self.problems(**over)
            self.assertTrue(any(fragment in e for e in errors), f"{name}: {errors}")

    def test_file_level_problems(self):
        for data in ([], {}, {"products": []}, {"products": "x"}, {"products": ["x"]}):
            _, errors = validate(data, set(CATS))
            self.assertTrue(errors, data)
        _, errors = validate({"products": [product(), product(brand="b", title="t")]}, set(CATS))
        self.assertTrue(any("duplicate of an earlier product" in e for e in errors))

    def test_underscore_fields_are_comments_and_valid_input_passes(self):
        data = {"_note": "hi", "products": [dict(product(), _comment="source: brand site")]}
        products, errors = validate(data, set(CATS))
        self.assertEqual((errors, len(products)), ([], 1))
        self.assertEqual(products[0]["sizes"][0]["chest_min"], 88.0)

    def test_load_file_errors(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            with self.assertRaises(CatalogDataError) as ctx:
                load_file(d / "missing.json")
            self.assertIn("File not found", ctx.exception.errors[0])
            (d / "bad.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(CatalogDataError) as ctx:
                load_file(d / "bad.json")
            self.assertIn("Invalid JSON", ctx.exception.errors[0])
            (d / "cp1251.json").write_bytes('{"products": [{"brand": "Жінка"}]}'.encode("cp1251"))
            with self.assertRaises(CatalogDataError) as ctx:
                load_file(d / "cp1251.json")
            self.assertIn("UTF-8", ctx.exception.errors[0])
            (d / "bom.json").write_bytes(b"\xef\xbb\xbf" + json.dumps({"products": [product()]}).encode())
            self.assertEqual(len(load_file(d / "bom.json")["products"]), 1)


class DefaultChartTests(ImportBase):
    def test_every_supported_combination_is_valid_and_sorted(self):
        combos = [(c, g) for c in FAMILY for g in ("male", "female", "unisex") if default_chart(c, g)]
        self.assertGreaterEqual(len(combos), 9)
        for cat, gender in combos:
            _, errors = validate({"products": [{"brand": "B", "title": f"{cat}{gender}", "category": cat,
                                                "gender": gender, "use_default_chart": True}]}, set(CATS))
            self.assertEqual(errors, [], (cat, gender))
            chart = default_chart(cat, gender)
            for zone in ("chest", "waist", "hips"):
                lows = [e[f"{zone}_min"] for e in chart if f"{zone}_min" in e]
                self.assertEqual(lows, sorted(lows), (cat, gender, zone))

    def test_unsupported_combinations_return_none(self):
        self.assertIsNone(default_chart("coats", "male"))
        self.assertIsNone(default_chart("dresses", "male"))

    def test_typical_bodies_get_a_fitting_size(self):
        from fitting.engine import recommend_size
        cases = [("tshirts", "male", 96, 82, 100), ("tshirts", "female", 90, 72, 98),
                 ("jeans", "male", 96, 82, 100), ("jeans", "female", 88, 70, 96), ("dresses", "female", 90, 72, 98)]
        for cat, gender, chest, waist, hips in cases:
            res = import_catalog({"products": [{"brand": "B", "title": f"{cat}{gender}", "category": cat,
                                                "gender": gender, "use_default_chart": True}]})
            p = Product.objects.prefetch_related("sizes").get(title=f"{cat}{gender}")
            rec = recommend_size(p, {"chest_circumference": chest, "waist_circumference": waist,
                                     "hip_circumference": hips})
            self.assertTrue(rec["fits"], (cat, gender, rec))


class ApproximateFlagTests(ImportBase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("a@example.com", "S3cure-pass-word", username="A", gender="male")
        self.avatar = Avatar.objects.create(
            user=self.user, name="Me", gender="male", age=25, height_cm=180, weight_kg=75, is_default=True,
            measurements={"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100})
        self.client.force_authenticate(self.user)
        import_catalog({"products": [product(title="Real", brand="Real"),
                                     product(title="Generic", brand="Generic", sizes=None, use_default_chart=True)]})

    def test_catalog_and_fit_evaluation_expose_approximate(self):
        cards = {c["title"]: c for c in self.client.get(reverse("products")).data["results"]}
        self.assertEqual((cards["Real"]["approximate"], cards["Real"]["size_chart_source"]), (False, "brand"))
        self.assertEqual((cards["Generic"]["approximate"], cards["Generic"]["size_chart_source"]), (True, "default"))
        self.assertTrue(cards["Generic"]["recommended_size"])
        for title, expected in (("Real", False), ("Generic", True)):
            pid = Product.objects.get(title=title).pk
            r = self.client.post(reverse("fit-evaluate"), {"product_id": pid}, format="json")
            self.assertEqual(r.data["approximate"], expected)

    def test_wardrobe_items_expose_approximate(self):
        sid = self.client.post(reverse("sessions"), {}, format="json").data["id"]
        pid = Product.objects.get(title="Generic").pk
        r = self.client.post(reverse("session-items", args=[sid]), {"product_id": pid}, format="json")
        self.assertTrue(r.data["items"][0]["approximate"])


PAGE_NO_TABLE = """<script type="application/ld+json">{"@type":"Product","name":"Soft Hoodie","brand":"NoChart",
"image":"https://cdn.example/h.jpg"}</script><html><body>no size table here</body></html>"""


class UrlImportFallbackTests(ImportBase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user("a@example.com", "S3cure-pass-word", username="A", gender="male")
        self.client.force_authenticate(self.user)
        self.url = reverse("product-import")

    def post(self, page=PAGE_NO_TABLE, **data):
        with mock.patch("catalog.views.fetch_html", return_value=page):
            return self.client.post(self.url, {"url": "https://shop.example/p1", **data}, format="json")

    def test_page_without_a_chart_gets_a_generic_one_marked_approximate(self):
        r = self.post(category="hoodies", gender="female")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["approximate"])
        self.assertEqual([s["label"] for s in r.data["sizes"]], ["XS", "S", "M", "L", "XL"])

    def test_category_can_be_guessed_from_the_title_and_unisex_uses_the_mens_chart(self):
        r = self.post()
        self.assertEqual((r.status_code, r.data["category"]), (201, "hoodies"))
        self.assertEqual([s["label"] for s in r.data["sizes"]], ["S", "M", "L", "XL"])

    def test_without_a_category_there_is_still_a_clear_error(self):
        page = PAGE_NO_TABLE.replace("Soft Hoodie", "Mystery Garment")
        r = self.post(page)
        self.assertEqual((r.status_code, r.data["code"]), (422, "size_chart_not_found"))

    def test_unsupported_category_gender_combination_is_an_error(self):
        r = self.post(category="dresses", gender="male")
        self.assertEqual(r.status_code, 422)

    def test_the_template_database_wins_over_the_generic_chart(self):
        import_catalog({"products": [product(brand="NoChart", title="Soft Hoodie", category="hoodies")]})
        r = self.post()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["approximate"])
        self.assertEqual(r.data["is_template"], True)


class CommandTests(ImportBase):
    def run_command(self, data, *args):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "catalog.json"
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            out = StringIO()
            call_command("import_catalog", str(path), *args, stdout=out)
            return out.getvalue()

    def test_success_dry_run_and_error_output(self):
        self.assertIn("[dry run] would be imported: 1 created", self.run_command({"products": [product()]}, "--dry-run"))
        self.assertEqual(Product.objects.count(), 0)
        self.assertIn("imported: 1 created, 0 updated", self.run_command({"products": [product()]}))
        self.assertIn("imported: 0 created, 1 updated", self.run_command({"products": [product()]}))
        with self.assertRaises(CommandError) as ctx:
            self.run_command({"products": [product(category="coats"), product(title="X", gender="z")]})
        self.assertIn("2 problem(s)", str(ctx.exception))
        self.assertIn("unknown category 'coats'", str(ctx.exception))
        self.assertEqual(Product.objects.count(), 1)