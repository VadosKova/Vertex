from django.test import SimpleTestCase
from django.urls import reverse

from catalog.models import Brand, Category, Product, ProductSize
from catalog.tests import CatalogBase

from .engine import build_verdict, evaluate_product, evaluate_zone, recommend_size


def z(zone, status, delta=0.0):
    return {"zone": zone, "status": status, "delta_cm": delta}


class VerdictWordingTests(SimpleTestCase):
    def test_all_good(self):
        zones = [z("chest", "perfect"), z("waist", "perfect")]
        self.assertEqual(build_verdict("M", zones, "uk"), "Розмір M сидить ідеально по всіх зонах.")
        self.assertEqual(build_verdict("M", zones, "en"), "Size M fits perfectly in all zones.")

    def test_some_good_some_problems_including_sleeves(self):
        zones = [z("chest", "perfect"), z("waist", "loose", 2.0), z("sleeve", "tight", 2.0)]
        self.assertEqual(build_verdict("M", zones, "uk"),
                         "Розмір M сидить ідеально у грудях, але у талії є запас 2 см, рукави коротші на 2 см.")
        self.assertEqual(build_verdict("M", zones, "en"),
                         "Size M fits perfectly in the chest, but there is 2 cm of extra room at the waist, "
                         "sleeves are 2 cm too short.")

    def test_loose_everywhere_matches_the_design_sentence(self):
        zones = [z("chest", "loose", 4.0), z("waist", "loose", 6.0), z("sleeve", "loose", 2.0)]
        self.assertEqual(build_verdict("L", zones, "uk"),
                         "Розмір L сидить вільно: запас 4 см у грудях і 6 см у талії, рукави довші на 2 см.")
        self.assertEqual(build_verdict("L", zones, "en"),
                         "Size L fits loosely: extra room: 4 cm in the chest and 6 cm at the waist, "
                         "sleeves are 2 cm too long.")

    def test_three_loose_zones_are_listed_with_commas(self):
        zones = [z("chest", "loose", 4.0), z("waist", "loose", 6.0), z("hips", "loose", 2.0)]
        self.assertEqual(build_verdict("L", zones, "uk"),
                         "Розмір L сидить вільно: запас 4 см у грудях, 6 см у талії і 2 см у стегнах.")

    def test_tight_everywhere(self):
        zones = [z("chest", "tight", 3.0), z("waist", "tight", 2.0)]
        self.assertEqual(build_verdict("S", zones, "uk"), "Розмір S тисне: бракує 3 см у грудях і 2 см у талії.")
        self.assertEqual(build_verdict("S", zones, "en"), "Size S is tight: short by 3 cm in the chest and 2 cm at the waist.")

    def test_mixed_without_a_good_zone(self):
        zones = [z("chest", "loose", 4.0), z("hips", "tight", 2.0)]
        self.assertEqual(build_verdict("M", zones, "uk"), "Розмір M: запас 4 см у грудях, але бракує 2 см у стегнах.")

    def test_only_a_sleeve_problem(self):
        self.assertEqual(build_verdict("L", [z("sleeve", "loose", 2.0)], "uk"), "Розмір L сидить вільно: рукави довші на 2 см.")
        self.assertEqual(build_verdict("L", [z("chest", "perfect"), z("sleeve", "loose", 3.0)], "uk"),
                         "Розмір L сидить ідеально у грудях, але рукави довші на 3 см.")

    def test_perfect_sleeves_are_named_in_the_good_list(self):
        zones = [z("chest", "perfect"), z("sleeve", "perfect"), z("waist", "loose", 2.0)]
        self.assertIn("у грудях і по довжині рукавів", build_verdict("M", zones, "uk"))

    def test_unknown_language_falls_back_to_ukrainian(self):
        self.assertTrue(build_verdict("M", [z("chest", "perfect")], "de").startswith("Розмір"))


class SleeveAndStretchRuleTests(SimpleTestCase):
    def test_sleeve_is_judged_like_the_other_zones(self):
        self.assertEqual(evaluate_zone("sleeve", 62, 60, 66, 0)["status"], "perfect")
        self.assertEqual(evaluate_zone("sleeve", 70, 60, 66, 0)["status"], "tight")
        r = evaluate_zone("sleeve", 56, 60, 66, 0)
        self.assertEqual((r["status"], r["delta_cm"]), ("loose", 4.0))


class SleeveEngineTests(CatalogBase):
    def setUp(self):
        super().setUp()
        brand = Brand.objects.create(name="B")
        cat = Category.objects.create(slug="hoodies", name_uk="Худі", name_en="Hoodies")
        self.hoodie = Product.objects.create(brand=brand, category=cat, title="Hoodie", fabric_stretch=0.1)
        for i, (label, sleeve) in enumerate({"M": (60, 64), "L": (64, 68)}.items()):
            ProductSize.objects.create(product=self.hoodie, label=label, order=i, chest_min=92, chest_max=100,
                                       waist_min=78, waist_max=86, hips_min=96, hips_max=102,
                                       sleeve_min=sleeve[0], sleeve_max=sleeve[1])
        self.hoodie = Product.objects.prefetch_related("sizes").get(pk=self.hoodie.pk)
        self.body = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}

    def test_the_sleeve_picks_the_size_and_appears_in_the_heatmap(self):
        rec = recommend_size(self.hoodie, {**self.body, "arm_length": 66})
        self.assertEqual(rec["label"], "L")
        self.assertIn("sleeve", {x["zone"] for x in rec["zones"]})
        rec = recommend_size(self.hoodie, {**self.body, "arm_length": 61})
        self.assertEqual(rec["label"], "M")

    def test_fabric_stretch_never_lengthens_a_sleeve(self):
        sizes = {r["label"]: r for r in evaluate_product(self.hoodie, {**self.body, "arm_length": 71})}
        self.assertEqual({x["zone"]: x["status"] for x in sizes["M"]["zones"]}["sleeve"], "tight")
        self.assertEqual({x["zone"]: x["status"] for x in sizes["L"]["zones"]}["sleeve"], "tight")

    def test_without_an_arm_length_the_estimate_is_used_and_flagged(self):
        from avatars.measurements import estimate_missing
        full, est = estimate_missing(180, "male", self.body)
        self.assertIn("arm_length", est)
        self.assertIsNotNone(recommend_size(self.hoodie, full))

    def test_sql_filter_agrees_with_the_engine_for_sleeves(self):
        from catalog.filtering import fitting_products
        for arm in (50, 56, 60, 64, 68, 70, 74, 80):
            m = {**self.body, "arm_length": arm}
            sql = fitting_products(Product.objects.all(), m).filter(pk=self.hoodie.pk).exists()
            py = any(r["fits"] for r in evaluate_product(self.hoodie, m))
            self.assertEqual(sql, py, f"arm {arm}")

    def test_bulk_import_and_the_size_table_parser_understand_sleeves(self):
        from catalog.importers import parse_product_page
        from catalog.importing import import_catalog
        out = parse_product_page("<table><tr><th>Розмір</th><th>Довжина рукава (см)</th><th>Обхват грудей</th></tr>"
                                 "<tr><td>M</td><td>60-64</td><td>92-100</td></tr></table>")
        self.assertEqual((out["sizes"][0]["sleeve_min"], out["sizes"][0]["sleeve_max"]), (60.0, 64.0))
        import_catalog({"products": [{"brand": "X", "title": "Long sleeve", "category": "tshirts", "gender": "male",
                                      "sizes": [{"label": "M", "chest": [92, 100], "sleeve": [60, 64]}]}]})
        self.assertEqual(ProductSize.objects.get(product__title="Long sleeve").sleeve_max, 64.0)
        from catalog.importing import CatalogDataError
        with self.assertRaises(CatalogDataError):
            import_catalog({"products": [{"brand": "X", "title": "Bad", "category": "tshirts", "gender": "male",
                                          "sizes": [{"label": "M", "sleeve": [10, 20]}]}]})


class EvaluateRecommendedTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.avatar = self.make_avatar()
        self.product = self.make_product()

    def test_chosen_size_comes_with_the_recommendation(self):
        r = self.client.post(reverse("fit-evaluate"), {"product_id": self.product.pk, "size": "L"}, format="json")
        self.assertEqual(r.data["result"]["label"], "L")
        self.assertEqual(r.data["recommended"], {"label": "M", "compatibility": 100, "fits": True})

    def test_recommended_is_the_same_when_no_size_is_chosen(self):
        r = self.client.post(reverse("fit-evaluate"), {"product_id": self.product.pk}, format="json")
        self.assertEqual(r.data["recommended"]["label"], r.data["result"]["label"])

    def test_a_poor_match_still_gets_a_recommendation_marked_as_not_fitting(self):
        p = self.make_product(title="Odd", chart={"S": ((80, 84), (60, 64), (80, 84))})
        r = self.client.post(reverse("fit-evaluate"), {"product_id": p.pk, "size": "S"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.data["recommended"])
        self.assertFalse(r.data["recommended"]["fits"])


class LayerTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.avatar = self.make_avatar()
        self.products = [self.make_product(title=t) for t in ("Tee", "Jeans", "Hoodie", "Jacket")]
        sid = self.client.post(reverse("sessions"), {}, format="json").data["id"]
        self.sid = sid
        for p in self.products[:3]:
            self.client.post(reverse("session-items", args=[sid]), {"product_id": p.pk}, format="json")

    def session(self):
        return self.client.get(reverse("session-detail", args=[self.sid])).data

    def titles(self):
        return [(i["title"], i["layer"]) for i in self.session()["items"]]

    def patch(self, item_id, **data):
        return self.client.patch(reverse("session-item", args=[self.sid, item_id]), data, format="json")

    def test_counters_for_the_layers_row(self):
        s = self.session()
        self.assertEqual((s["layers_count"], s["layers_limit"], s["visible_count"]), (3, 4, 3))
        item = s["items"][0]["id"]
        self.patch(item, visible=False)
        self.assertEqual(self.session()["visible_count"], 2)

    def test_item_rows_carry_what_the_screen_shows(self):
        item = self.session()["items"][0]
        for key in ("brand", "image_url", "shop_url", "price", "currency", "size", "recommended_size", "fit",
                    "garment_model_url", "approximate"):
            self.assertIn(key, item)
        self.assertEqual((item["brand"], item["recommended_size"], item["size"]), ("Brandy", "M", "M"))
        self.assertTrue(item["fit"]["zones"])

    def test_layers_are_renumbered_after_a_removal(self):
        ids = [i["id"] for i in self.session()["items"]]
        self.assertEqual(self.client.delete(reverse("session-item", args=[self.sid, ids[0]])).status_code, 204)
        self.assertEqual(self.titles(), [("Jeans", 0), ("Hoodie", 1)])

        for p in (self.products[0], self.products[3]):
            self.client.post(reverse("session-items", args=[self.sid]), {"product_id": p.pk}, format="json")
        self.assertEqual(self.titles(), [("Jeans", 0), ("Hoodie", 1), ("Tee", 2), ("Jacket", 3)])

    def test_moving_a_layer(self):
        ids = {i["title"]: i["id"] for i in self.session()["items"]}
        r = self.patch(ids["Hoodie"], layer=0)
        self.assertEqual([(i["title"], i["layer"]) for i in r.data["items"]], [("Hoodie", 0), ("Tee", 1), ("Jeans", 2)])
        r = self.patch(ids["Hoodie"], layer=2)
        self.assertEqual([(i["title"], i["layer"]) for i in r.data["items"]], [("Tee", 0), ("Jeans", 1), ("Hoodie", 2)])
        self.assertEqual(self.patch(ids["Tee"], layer=3).status_code, 400)
        self.assertEqual(self.patch(ids["Tee"], layer=-1).status_code, 400)

    def test_size_label_is_stored_in_canonical_case(self):
        item = self.session()["items"][0]["id"]
        r = self.patch(item, size_label="l")
        self.assertEqual(r.data["items"][0]["size"], "L")
        self.assertEqual(self.patch(item, size_label="XXL").status_code, 400)

    def test_several_changes_in_one_patch(self):
        ids = {i["title"]: i["id"] for i in self.session()["items"]}
        r = self.patch(ids["Jeans"], visible=False, size_label="s", layer=0)
        first = r.data["items"][0]
        self.assertEqual((first["title"], first["visible"], first["size"], first["layer"]), ("Jeans", False, "S", 0))

    def test_unknown_fields_are_ignored_and_foreign_items_untouchable(self):
        item = self.session()["items"][0]["id"]
        self.assertEqual(self.patch(item, product_id=self.products[3].pk, size_label=None).status_code, 400)
        self.assertEqual(self.patch(item, product_id=self.products[3].pk).status_code, 200)
        self.assertEqual(self.session()["items"][0]["title"], "Tee")
        self.client.force_authenticate(self.other)
        self.assertEqual(self.patch(item, visible=False).status_code, 404)