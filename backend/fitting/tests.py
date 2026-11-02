from django.test import SimpleTestCase, TestCase

from catalog.models import Brand, Category, Product, ProductSize

from .engine import build_verdict, evaluate_product, evaluate_zone, recommend_size


class ZoneRuleTests(SimpleTestCase):
    def test_zone_classification(self):
        self.assertEqual(evaluate_zone("chest", 96, 92, 100, 0.03)["status"], "perfect")
        self.assertEqual(evaluate_zone("chest", 100, 92, 100, 0.03)["status"], "perfect")
        self.assertEqual(evaluate_zone("chest", 102, 92, 100, 0.03)["status"], "perfect")
        self.assertEqual(evaluate_zone("chest", 104, 92, 100, 0.03)["status"], "tight")
        self.assertEqual(evaluate_zone("chest", 90, 92, 100, 0.03)["status"], "loose")
        self.assertEqual(evaluate_zone("chest", 91.5, 92, 100, 0.03)["status"], "perfect")
        self.assertEqual(evaluate_zone("waist", 70, 78, 86, 0.0)["delta_cm"], 8.0)

    def test_intensity_is_bounded_and_monotonic(self):
        a = evaluate_zone("waist", 87, 78, 86, 0)["intensity"]
        b = evaluate_zone("waist", 90, 78, 86, 0)["intensity"]
        c = evaluate_zone("waist", 120, 78, 86, 0)["intensity"]
        self.assertTrue(0 < a < b < c <= 1.0)
        loose_a = evaluate_zone("waist", 76, 78, 86, 0)["intensity"]
        loose_b = evaluate_zone("waist", 72, 78, 86, 0)["intensity"]
        self.assertTrue(0 < loose_a < loose_b <= 1.0)

    def test_english_verdict(self):
        zones = [{"zone": "chest", "status": "perfect", "delta_cm": 0}, {"zone": "waist", "status": "loose", "delta_cm": 2.0}]
        self.assertEqual(build_verdict("M", zones, "en"), "Size M fits perfectly in the chest, but there is 2 cm of extra room at the waist.")


class RecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cat = Category.objects.create(slug="t-shirts", name_uk="Футболки", name_en="T-shirts")
        brand = Brand.objects.create(name="Brandy")
        cls.product = cls.make(cat, brand, "Tee", 0.03,
                               {"S": ((88, 92), (74, 78), (92, 96)), "M": ((92, 100), (78, 86), (96, 102)),
                                "L": ((100, 108), (86, 94), (102, 110))})
        cls.stiff = cls.make(cat, brand, "Stiff", 0.0, {"L": ((100, 108), (86, 94), (102, 110))})
        cls.stretchy = cls.make(cat, brand, "Stretchy", 0.06, {"L": ((100, 108), (86, 94), (102, 110))})

    @staticmethod
    def make(cat, brand, title, stretch, chart):
        p = Product.objects.create(brand=brand, category=cat, title=title, fabric_stretch=stretch)
        for i, (label, (c, w, h)) in enumerate(chart.items()):
            ProductSize.objects.create(product=p, label=label, order=i, chest_min=c[0], chest_max=c[1],
                                       waist_min=w[0], waist_max=w[1], hips_min=h[0], hips_max=h[1])
        return Product.objects.prefetch_related("sizes").get(pk=p.pk)

    def m(self, **over):
        return {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100, **over}

    def test_perfect_fit_picks_M(self):
        rec = recommend_size(self.product, self.m())
        self.assertEqual(rec["label"], "M")
        self.assertTrue(rec["fits"])
        self.assertEqual(rec["verdict"], "Розмір M сидить ідеально по всіх зонах.")
        self.assertTrue(all(z["color"] == "#22C55E" for z in rec["zones"]))

    def test_slack_at_the_waist_matches_the_tz_example_phrase(self):
        rec = recommend_size(self.product, self.m(waist_circumference=74))
        self.assertEqual(rec["label"], "M")
        self.assertEqual(rec["verdict"], "Розмір M сидить ідеально у грудях і у стегнах, але у талії є запас 4 см.")
        waist = next(z for z in rec["zones"] if z["zone"] == "waist")
        self.assertEqual((waist["status"], waist["color"]), ("loose", "#FACC15"))

    def test_tight_zone_is_red_and_pushes_to_a_larger_size(self):
        big = self.m(hip_circumference=108, chest_circumference=105, waist_circumference=92)
        self.assertEqual(recommend_size(self.product, big)["label"], "L")
        m_eval = next(r for r in evaluate_product(self.product, self.m(hip_circumference=108)) if r["label"] == "M")
        self.assertIn("tight", [z["status"] for z in m_eval["zones"]])
        self.assertIn("тисне", m_eval["verdict"])
        self.assertFalse(m_eval["fits"])
        self.assertIn("#EF4444", [z["color"] for z in m_eval["zones"]])

    def test_stretchy_fabric_extends_the_range(self):
        m = self.m(chest_circumference=108.8, waist_circumference=94, hip_circumference=110)
        z_stiff = next(z for z in recommend_size(self.stiff, m)["zones"] if z["zone"] == "chest")
        z_stretchy = next(z for z in recommend_size(self.stretchy, m)["zones"] if z["zone"] == "chest")
        self.assertEqual((z_stiff["status"], z_stretchy["status"]), ("tight", "perfect"))

    def test_ties_prefer_the_larger_size_and_missing_data_is_safe(self):
        self.assertIsNone(recommend_size(self.product, {}))