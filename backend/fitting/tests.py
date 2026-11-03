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
        cat = Category.objects.create(slug="tshirts", name_uk="Футболки", name_en="T-shirts")
        brand = Brand.objects.create(name="Brandy")
        cls.product = cls.make(cat, brand, "Tee", 0.03,
                               {"S": ((88, 92), (74, 78), (92, 96)), "M": ((92, 100), (78, 86), (96, 102)),
                                "L": ((100, 108), (86, 94), (102, 110))})
        cls.stiff = cls.make(cat, brand, "Stiff", 0.0, {"L": ((100, 108), (86, 94), (102, 110))})
        cls.stretchy = cls.make(cat, brand, "Stretchy", 0.06, {"L": ((100, 108), (86, 94), (102, 110))})
        cls.tie = cls.make(cat, brand, "Tie", 0.03, {"M": ((90, 100), (78, 86), (96, 102)),
                                                     "L": ((92, 102), (78, 86), (96, 102))})

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

    def test_ties_prefer_the_larger_size(self):
        evals = {r["label"]: r["score"] for r in evaluate_product(self.tie, self.m())}
        self.assertEqual(evals["M"], evals["L"])
        self.assertEqual(recommend_size(self.tie, self.m())["label"], "L")

    def test_missing_measurements_give_no_recommendation(self):
        self.assertIsNone(recommend_size(self.product, {}))


# --HTTP API--
from django.urls import reverse

from catalog.tests import CatalogBase

from .models import TryOnItem


class EvaluateEndpointTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.avatar = self.make_avatar()
        self.product = self.make_product()

    def post(self, **data):
        return self.client.post(reverse("fit-evaluate"), data, format="json")

    def test_recommended_size_zones_and_ranked_sizes(self):
        r = self.post(product_id=self.product.pk)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["result"]["label"], "M")
        self.assertTrue(r.data["result"]["fits"])
        self.assertEqual([s["label"] for s in r.data["sizes"]], ["S", "M", "L"])
        self.assertIn("shoulder_width", r.data["estimated_fields"])
        self.assertEqual({z["zone"] for z in r.data["result"]["zones"]}, {"chest", "waist", "hips"})

    def test_specific_size_and_language(self):
        r = self.post(product_id=self.product.pk, size="s", lang="en")
        self.assertEqual(r.data["result"]["label"], "S")
        self.assertTrue(r.data["result"]["verdict"].startswith("Size S"))

    def test_account_language_is_the_default(self):
        self.user.language = "en"
        self.user.save()
        self.assertTrue(self.post(product_id=self.product.pk).data["result"]["verdict"].startswith("Size"))
        self.user.language = "uk"
        self.user.save()
        self.assertTrue(self.post(product_id=self.product.pk).data["result"]["verdict"].startswith("Розмір"))

    def test_other_avatar_can_be_chosen(self):
        big = self.make_avatar(name="Big", is_default=False, measurements={
            "chest_circumference": 105, "waist_circumference": 92, "hip_circumference": 108})
        r = self.post(product_id=self.product.pk, avatar_id=str(big.pk))
        self.assertEqual(r.data["result"]["label"], "L")

    def test_errors(self):
        self.assertEqual(self.post(product_id=self.product.pk, size="XXL").status_code, 400)
        self.assertEqual(self.post(product_id=99999).status_code, 404)
        self.assertEqual(self.client.post(reverse("fit-evaluate"), {}, format="json").status_code, 400)
        foreign = self.make_avatar(user=self.other, is_default=False)
        self.assertEqual(self.post(product_id=self.product.pk, avatar_id=str(foreign.pk)).status_code, 404)

    def test_no_avatar_gives_404_and_no_size_chart_gives_422(self):
        empty = self.make_product(title="Empty")
        empty.sizes.all().delete()
        self.assertEqual(self.post(product_id=empty.pk).status_code, 422)
        self.avatar.delete()
        self.assertEqual(self.post(product_id=self.product.pk).status_code, 404)

    def test_cannot_evaluate_another_users_imported_product(self):
        private = self.make_product(owner=self.other, title="Secret")
        self.assertEqual(self.post(product_id=private.pk).status_code, 404)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post(product_id=self.product.pk).status_code, 401)


class WardrobeSessionTests(CatalogBase):
    def setUp(self):
        super().setUp()
        self.avatar = self.make_avatar()
        self.tee = self.make_product(title="Tee")
        self.hoodie = self.make_product(title="Hoodie", slug="hoodies")

    def new_session(self):
        r = self.client.post(reverse("sessions"), {}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def add(self, sid, product, **extra):
        return self.client.post(reverse("session-items", args=[sid]), {"product_id": product.pk, **extra}, format="json")

    def test_layers_toggle_resize_and_remove(self):
        sid = self.new_session()
        self.add(sid, self.tee)
        r = self.add(sid, self.hoodie, size="L")
        items = r.data["items"]
        self.assertEqual([(i["title"], i["size"], i["layer"]) for i in items], [("Tee", "M", 0), ("Hoodie", "L", 1)])
        self.assertTrue(items[0]["fit"]["zones"])
        iid = items[1]["id"]
        r = self.client.patch(reverse("session-item", args=[sid, iid]), {"visible": False}, format="json")
        self.assertFalse(next(i for i in r.data["items"] if i["id"] == iid)["visible"])
        r = self.client.patch(reverse("session-item", args=[sid, iid]), {"size_label": "S"}, format="json")
        self.assertEqual(next(i for i in r.data["items"] if i["id"] == iid)["size"], "S")
        bad = self.client.patch(reverse("session-item", args=[sid, iid]), {"size_label": "XXL"}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.delete(reverse("session-item", args=[sid, iid])).status_code, 204)
        self.assertEqual(len(self.client.get(reverse("session-detail", args=[sid])).data["items"]), 1)

    def test_item_fit_follows_the_chosen_size(self):
        sid = self.new_session()
        items = self.add(sid, self.tee, size="S").data["items"]
        statuses = {z["zone"]: z["status"] for z in items[0]["fit"]["zones"]}
        self.assertEqual(statuses["chest"], "tight")

    def test_same_item_twice_and_item_limit(self):
        sid = self.new_session()
        self.assertEqual(self.add(sid, self.tee).status_code, 201)
        self.assertEqual(self.add(sid, self.tee).status_code, 409)
        for i in range(9):
            self.assertEqual(self.add(sid, self.make_product(title=f"P{i}")).status_code, 201)
        self.assertEqual(self.add(sid, self.make_product(title="One too many")).status_code, 400)

    def test_session_list_delete_and_missing_avatar(self):
        sid = self.new_session()
        self.assertEqual(len(self.client.get(reverse("sessions")).data), 1)
        self.assertEqual(self.client.delete(reverse("session-detail", args=[sid])).status_code, 204)
        self.assertEqual(self.client.get(reverse("session-detail", args=[sid])).status_code, 404)
        self.avatar.delete()
        self.assertEqual(self.client.post(reverse("sessions"), {}, format="json").status_code, 404)

    def test_sessions_are_private(self):
        sid = self.new_session()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("session-detail", args=[sid])).status_code, 404)
        self.assertEqual(self.add(sid, self.tee).status_code, 404)
        self.assertEqual(self.client.delete(reverse("session-detail", args=[sid])).status_code, 404)
        self.assertEqual(self.client.get(reverse("sessions")).data, [])

    def test_cannot_use_another_users_imported_product_or_avatar(self):
        private = self.make_product(owner=self.other, title="Secret")
        sid = self.new_session()
        self.assertEqual(self.add(sid, private).status_code, 404)
        foreign = self.make_avatar(user=self.other, is_default=False)
        r = self.client.post(reverse("sessions"), {"avatar_id": str(foreign.pk)}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_items_cannot_be_modified_through_another_session_url(self):
        sid, other_sid = self.new_session(), self.new_session()
        iid = self.add(sid, self.tee).data["items"][0]["id"]
        r = self.client.patch(reverse("session-item", args=[other_sid, iid]), {"visible": False}, format="json")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(TryOnItem.objects.get(pk=iid).visible)

    def test_deleting_the_avatar_removes_its_sessions(self):
        sid = self.new_session()
        self.avatar.delete()
        self.assertEqual(self.client.get(reverse("session-detail", args=[sid])).status_code, 404)