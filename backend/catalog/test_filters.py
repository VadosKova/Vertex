from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from fitting.engine import compatibility, recommend_size

from .importers import parse_product_page
from .importing import CatalogDataError, import_catalog, validate
from .models import Category, Product
from .tests import CatalogBase


def priced(product, price=None, old=None, fit="regular", currency="UAH"):
    Product.objects.filter(pk=product.pk).update(price=price, old_price=old, fit_type=fit, currency=currency)
    return Product.objects.get(pk=product.pk)


class CompatibilityTests(CatalogBase):
    def test_percentage_formula(self):
        self.assertEqual(compatibility(0, True), 100)
        self.assertEqual(compatibility(2, True), 98)
        self.assertEqual(compatibility(35, True), 65)
        self.assertEqual(compatibility(500, True), 0)
        self.assertEqual(compatibility(1, False), 79)
        self.assertEqual(compatibility(30, False), 70)

    def test_engine_reports_it_per_size_and_for_the_recommendation(self):
        p = Product.objects.prefetch_related("sizes").get(pk=self.make_product().pk)
        m = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}
        self.assertEqual(recommend_size(p, m)["compatibility"], 100)
        slack = recommend_size(p, {**m, "waist_circumference": 76})
        self.assertEqual((slack["label"], slack["compatibility"]), ("M", 98))
        tight = recommend_size(p, {**m, "chest_circumference": 120, "waist_circumference": 110, "hip_circumference": 125})
        self.assertFalse(tight["fits"])
        self.assertLessEqual(tight["compatibility"], 79)

    def test_cards_show_compatibility_and_it_matches_the_evaluate_endpoint(self):
        self.make_avatar()
        product = self.make_product()
        card = self.client.get(reverse("products")).data["results"][0]
        self.assertEqual((card["recommended_size"], card["compatibility"]), ("M", 100))
        ev = self.client.post(reverse("fit-evaluate"), {"product_id": product.pk}, format="json").data
        self.assertEqual(ev["result"]["compatibility"], card["compatibility"])
        self.assertEqual({s["label"]: s["compatibility"] for s in ev["sizes"]}["M"], 100)

    def test_no_avatar_means_no_compatibility(self):
        self.make_product()
        card = self.client.get(reverse("products")).data["results"][0]
        self.assertEqual((card["recommended_size"], card["compatibility"]), (None, None))


class CardFieldsTests(CatalogBase):
    def test_price_discount_currency_and_fit(self):
        p = priced(self.make_product(title="Hoodie"), price=Decimal("1160"), old=Decimal("1450"), fit="loose")
        card = self.client.get(reverse("product-detail", args=[p.pk])).data
        self.assertEqual((card["price"], card["old_price"], card["currency"], card["fit_type"]),
                         (1160.0, 1450.0, "UAH", "loose"))
        self.assertEqual(card["discount_percent"], 20)

    def test_products_without_prices_are_fine(self):
        p = self.make_product(title="No price")
        card = self.client.get(reverse("product-detail", args=[p.pk])).data
        self.assertEqual((card["price"], card["old_price"], card["discount_percent"]), (None, None, None))
        self.assertEqual((card["currency"], card["fit_type"]), ("UAH", "regular"))

    def test_old_price_not_above_price_gives_no_discount(self):
        p = priced(self.make_product(), price=Decimal("500"), old=Decimal("500"))
        self.assertIsNone(self.client.get(reverse("product-detail", args=[p.pk])).data["discount_percent"])


class FilterTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.make_avatar()
        self.tee = priced(self.make_product(title="Tee", gender="male"), Decimal("500"), fit="slim")
        self.hoodie = priced(self.make_product(title="Hoodie", slug="hoodies", gender="unisex"),
                             Decimal("1500"), Decimal("1875"), fit="loose")
        self.her = priced(self.make_product(title="Her Tee", gender="female"), Decimal("900"), fit="regular")
        self.unpriced = self.make_product(title="Unpriced")
        self.xl_only = priced(self.make_product(title="XL only", chart={"XL": ((108, 116), (94, 102), (110, 118)),
                                                                       "M": ((92, 100), (78, 86), (96, 102))}),
                              Decimal("700"))

    def titles(self, **params):
        r = self.client.get(reverse("products"), params)
        self.assertEqual(r.status_code, 200, r.data)
        return {p["title"] for p in r.data["results"]}

    def test_gender_as_in_the_avatar_by_default_and_explicit_choices_override(self):
        self.assertEqual(self.titles(), {"Tee", "Hoodie", "Unpriced", "XL only"})
        self.assertEqual(self.titles(gender="female"), {"Her Tee"})
        self.assertEqual(self.titles(gender="male,female"), {"Tee", "Her Tee"})
        self.assertEqual(self.titles(gender="unisex,male", personalized="false"),
                         {"Tee", "Hoodie", "Unpriced", "XL only"})

    def test_size_filter_matches_labels_case_insensitively(self):
        self.assertEqual(self.titles(sizes="XL"), {"XL only"})
        self.assertEqual(self.titles(sizes="xl"), {"XL only"})
        self.assertEqual(self.titles(sizes="S,XL"), {"Tee", "Hoodie", "Unpriced", "XL only"})
        self.assertEqual(self.titles(sizes="XXL"), set())

    def test_fit_filter(self):
        self.assertEqual(self.titles(fit="slim"), {"Tee"})
        self.assertEqual(self.titles(fit="slim,loose"), {"Tee", "Hoodie"})

    def test_price_range_excludes_unpriced_products_only_when_used(self):
        self.assertEqual(self.titles(min_price="600", max_price="1000", gender="male,female,unisex"), {"Her Tee", "XL only"})
        self.assertEqual(self.titles(max_price="500"), {"Tee"})
        self.assertIn("Unpriced", self.titles())

    def test_min_compat_hides_weak_matches(self):
        self.assertEqual(self.titles(min_compat="100"), {"Tee", "Hoodie", "Unpriced", "XL only"})
        low = self.make_avatar(name="Wide", is_default=False, measurements={
            "chest_circumference": 104, "waist_circumference": 90, "hip_circumference": 108})
        r = self.client.get(reverse("products"), {"avatar": str(low.pk), "min_compat": 100})
        self.assertTrue(all(c["compatibility"] >= 100 for c in r.data["results"]))

    def test_filters_combine(self):
        self.assertEqual(self.titles(fit="loose", category="hoodies", max_price="2000"), {"Hoodie"})
        self.assertEqual(self.titles(q="tee", gender="female"), {"Her Tee"})

    def test_bad_query_values_are_a_clear_400(self):
        for params in ({"gender": "robot"}, {"fit": "baggy"}, {"min_compat": "101"}, {"min_compat": "-1"},
                       {"min_price": "-5"}, {"min_price": "abc"}, {"min_price": "900", "max_price": "100"},
                       {"ordering": "random"}, {"personalized": "maybe"}, {"avatar": "garbage"},
                       {"sizes": ",".join(f"S{i}" for i in range(30))}):
            r = self.client.get(reverse("products"), params)
            self.assertEqual(r.status_code, 400, params)

    def test_unknown_and_foreign_avatar_ids_look_the_same(self):
        foreign = self.make_avatar(user=self.other, is_default=False)
        r1 = self.client.get(reverse("products"), {"avatar": str(foreign.pk)})
        r2 = self.client.get(reverse("products"), {"avatar": "00000000-0000-0000-0000-000000000000"})
        self.assertEqual((r1.status_code, r2.status_code), (404, 404))
        self.assertEqual(r1.data, r2.data)
        self.assertEqual(self.client.get(reverse("categories"), {"avatar": str(foreign.pk)}).status_code, 404)


class OrderingTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.make_avatar()
        self.best = priced(self.make_product(title="Best"), Decimal("800"))
        self.loose = priced(self.make_product(title="Loose", chart={"L": ((100, 108), (86, 94), (102, 110))}),
                            Decimal("300"))
        self.free = self.make_product(title="Unpriced")

    def order(self, **params):
        r = self.client.get(reverse("products"), params)
        self.assertEqual(r.status_code, 200, r.data)
        return [p["title"] for p in r.data["results"]]

    def test_default_is_by_compatibility_when_there_is_an_avatar(self):
        titles = self.order()
        self.assertEqual(titles[-1], "Loose")
        self.assertEqual(set(titles[:2]), {"Best", "Unpriced"})
        ranked = [(p["title"], p["compatibility"]) for p in self.client.get(reverse("products")).data["results"]]
        self.assertEqual([c for _, c in ranked], sorted((c for _, c in ranked), reverse=True))

    def test_new_price_asc_price_desc(self):
        self.assertEqual(self.order(ordering="new"), ["Unpriced", "Loose", "Best"])
        self.assertEqual(self.order(ordering="price_asc"), ["Loose", "Best", "Unpriced"])
        self.assertEqual(self.order(ordering="price_desc"), ["Best", "Loose", "Unpriced"])

    def test_price_ordering_also_works_together_with_min_compat(self):
        self.assertEqual(self.order(ordering="price_asc", min_compat=0, personalized="false"),
                         ["Loose", "Best", "Unpriced"])

    def test_without_an_avatar_the_default_is_newest_and_compat_ordering_falls_back(self):
        self.client.force_authenticate(self.other)
        self.assertEqual(self.order(), ["Unpriced", "Loose", "Best"])
        self.assertEqual(self.order(ordering="compat"), ["Unpriced", "Loose", "Best"])

    def test_pagination_keeps_the_compat_order(self):
        for i in range(25):
            self.make_product(title=f"Bulk {i}")
        first = self.client.get(reverse("products"), {"page_size": 10}).data
        second = self.client.get(reverse("products"), {"page_size": 10, "page": 2}).data
        scores = [p["compatibility"] for p in first["results"] + second["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(first["count"], 28)
        self.assertEqual(len({p["id"] for p in first["results"] + second["results"]}), 20)

    def test_query_count_is_constant_for_compat_ordering(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.client.get(reverse("products"))
            return len(ctx)
        base = count()
        for i in range(15):
            self.make_product(title=f"Extra {i}")
        self.assertLessEqual(count(), base + 1)


class CategoryCountTests(CatalogBase):
    def setUp(self):
        super().setUp()
        for slug in ("tshirts", "hoodies", "jeans", "dresses"):
            Category.objects.get_or_create(slug=slug, defaults={"name_uk": slug, "name_en": slug})
        self.make_avatar()
        for i in range(3):
            self.make_product(title=f"Tee {i}")
        for i in range(2):
            priced(self.make_product(title=f"Hoodie {i}", slug="hoodies"), Decimal("1000"), fit="loose")
        self.make_product(title="Huge", slug="hoodies", chart={"XXL": ((130, 140), (120, 130), (130, 140))})
        self.make_product(title="Her dress", slug="dresses", gender="female")

    def counts(self, **params):
        r = self.client.get(reverse("categories"), params)
        self.assertEqual(r.status_code, 200, r.data)
        return {c["slug"]: c["count"] for c in r.data}

    def test_counts_follow_personalisation(self):
        self.assertEqual(self.counts(), {"tshirts": 3, "hoodies": 2, "jeans": 0, "dresses": 0})
        self.assertEqual(self.counts(personalized="false"), {"tshirts": 3, "hoodies": 3, "jeans": 0, "dresses": 1})

    def test_counts_follow_the_other_filters_but_ignore_the_category_itself(self):
        self.assertEqual(self.counts(fit="loose")["hoodies"], 2)
        self.assertEqual(self.counts(fit="loose")["tshirts"], 0)
        self.assertEqual(self.counts(category="hoodies")["tshirts"], 3)

    def test_counts_equal_what_the_list_returns(self):
        for slug, n in self.counts().items():
            self.assertEqual(self.client.get(reverse("products"), {"category": slug}).data["count"], n, slug)

    def test_bad_params_and_private_products(self):
        self.assertEqual(self.client.get(reverse("categories"), {"gender": "robot"}).status_code, 400)
        self.make_product(title="Secret", owner=self.other)
        self.assertEqual(self.counts()["tshirts"], 3)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("categories")).status_code, 401)


class PriceImportTests(CatalogBase):
    def page(self, offers):
        import json
        ld = {"@type": "Product", "name": "Tee", "brand": "B", "offers": offers}
        return f'<script type="application/ld+json">{json.dumps(ld)}</script>'

    def test_price_formats_in_schema_org_offers(self):
        cases = [({"price": "1450", "priceCurrency": "UAH"}, (Decimal("1450.00"), "UAH")),
                 ({"price": 1450.5, "priceCurrency": "uah"}, (Decimal("1450.50"), "UAH")),
                 ({"price": "1 450,00", "priceCurrency": "UAH"}, (Decimal("1450.00"), "UAH")),
                 ([{"price": "19.99", "priceCurrency": "USD"}], (Decimal("19.99"), "USD")),
                 ({"lowPrice": "300", "priceCurrency": "EUR"}, (Decimal("300.00"), "EUR")),
                 ({"price": "99"}, (Decimal("99.00"), "UAH"))]
        for offers, expected in cases:
            out = parse_product_page(self.page(offers))
            self.assertEqual((out["price"], out["currency"]), expected, offers)

    def test_unusable_prices_are_ignored(self):
        for offers in ({"price": "free", "priceCurrency": "UAH"}, {"price": "-5", "priceCurrency": "UAH"},
                       {"price": "10", "priceCurrency": "XXX"}, {"price": "99999999999"}, "text", None, []):
            out = parse_product_page(self.page(offers))
            self.assertIsNone(out["price"], offers)

    def test_a_url_import_stores_the_price(self):
        from unittest import mock
        html = self.page({"price": "1 450,00", "priceCurrency": "UAH"}).replace(
            '"name": "Tee"', '"name": "Basic Tee"') + "<table><tr><th>Size</th><th>Chest</th></tr><tr><td>M</td><td>92-100</td></tr></table>"
        Category.objects.get_or_create(slug="tshirts", defaults={"name_uk": "Футболки", "name_en": "T-shirts"})
        with mock.patch("catalog.views.fetch_html", return_value=html):
            r = self.client.post(reverse("product-import"), {"url": "https://shop.example/tee"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["price"], r.data["currency"]), (1450.0, "UAH"))


class BulkImportPriceTests(CatalogBase):
    def setUp(self):
        super().setUp()
        for slug in ("tshirts", "hoodies", "jeans", "dresses"):
            Category.objects.get_or_create(slug=slug, defaults={"name_uk": slug, "name_en": slug})

    def item(self, **over):
        base = {"brand": "B", "title": "T", "category": "tshirts", "gender": "male", "use_default_chart": True}
        base.update(over)
        return base

    def test_prices_currency_and_fit_are_imported_and_updated(self):
        import_catalog({"products": [self.item(price=1160, old_price=1450, currency="USD", fit_type="slim")]})
        p = Product.objects.get(title="T")
        self.assertEqual((p.price, p.old_price, p.currency, p.fit_type),
                         (Decimal("1160.00"), Decimal("1450.00"), "USD", "slim"))
        import_catalog({"products": [self.item(price=900)]})
        p.refresh_from_db()
        self.assertEqual((p.price, p.old_price, p.currency, p.fit_type), (Decimal("900.00"), None, "UAH", "regular"))

    def test_validation(self):
        cases = [({"price": "cheap"}, "'price' must be a number"), ({"price": -1}, "'price' must be a number"),
                 ({"old_price": 100}, "'old_price' needs a 'price'"),
                 ({"price": 100, "old_price": 100}, "greater than it"), ({"price": 100, "old_price": 50}, "greater than it"),
                 ({"currency": "BTC"}, "'currency' must be one of"), ({"fit_type": "baggy"}, "'fit_type' must be one of")]
        for over, fragment in cases:
            _, errors = validate({"products": [self.item(**over)]}, {"tshirts"})
            self.assertTrue(any(fragment in e for e in errors), (over, errors))

    def test_example_file_has_prices(self):
        from pathlib import Path
        from .importing import load_file
        data = load_file(Path(__file__).resolve().parent / "data" / "example_catalog.json")
        import_catalog(data)
        self.assertTrue(Product.objects.filter(price__isnull=False).exists())
        self.assertTrue(Product.objects.filter(old_price__isnull=False).exists())
        self.assertEqual(set(Product.objects.values_list("fit_type", flat=True)) - {"slim", "regular", "loose"}, set())