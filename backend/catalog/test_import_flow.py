import json
from unittest import mock

import requests
from django.core import signing
from django.urls import reverse

from . import importers
from .importers import PageImportError, fetch_html, guess_category_slug, parse_product_page, register_adapter
from .importflow import TOKEN_SALT
from .models import Brand, Category, Product
from .shops import listed_shops, shop_for
from .tests import CatalogBase


def page(title="Slim Fit Jeans", brand="DenimCo", price="1450", sizes=True):
    ld = {"@type": "Product", "name": title, "brand": brand, "image": "https://cdn.example/p.jpg",
          "offers": {"price": price, "priceCurrency": "UAH"}}
    table = ("<table><tr><th>Size</th><th>Waist</th><th>Hips</th></tr>"
             "<tr><td>30</td><td>74-79</td><td>92-97</td></tr><tr><td>32</td><td>79-85</td><td>97-102</td></tr></table>"
             if sizes else "")
    return f'<script type="application/ld+json">{json.dumps(ld)}</script>{table}'


URL = "https://www.rozetka.com.ua/ua/men/jeans-slim-p123/"


class ImportBase(CatalogBase):
    def setUp(self):
        super().setUp()
        for slug in ("tshirts", "hoodies", "jeans", "dresses"):
            Category.objects.get_or_create(slug=slug, defaults={"name_uk": slug, "name_en": slug})

    def preview(self, html=None, url=URL, **extra):
        with mock.patch("catalog.views.fetch_html", return_value=html or page()) as fh:
            r = self.client.post(reverse("product-import-preview"), {"url": url, **extra}, format="json")
        return r, fh

    def confirm(self, **data):
        with mock.patch("catalog.views.fetch_html", side_effect=AssertionError("must not download again")):
            return self.client.post(reverse("product-import"), data, format="json")


class PreviewTests(ImportBase):
    def test_preview_describes_the_product_and_saves_nothing(self):
        self.make_avatar(measurements={"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100})
        r, _ = self.preview()
        self.assertEqual(r.status_code, 200, r.data)
        d = r.data
        self.assertEqual((d["title"], d["brand"], d["price"], d["currency"]), ("Slim Fit Jeans", "DenimCo", 1450.0, "UAH"))
        self.assertEqual((d["shop"]["name"], d["category"], d["needs_category"]), ("Rozetka", "jeans", False))
        self.assertEqual((d["size_chart_source"], d["approximate"], d["size_range"]), ("brand", False, "30–32"))
        self.assertEqual(d["sizes"][0], {"label": "30", "ranges": {"waist": [74.0, 79.0], "hips": [92.0, 97.0]}})
        self.assertEqual((d["recommended_size"], d["compatibility"]), ("32", 100))
        self.assertEqual((d["product_id"], d["already_in_catalog"]), (None, False))
        self.assertTrue(d["preview_token"])
        self.assertEqual(Product.objects.count(), 0)

    def test_without_an_avatar_there_is_no_match_number(self):
        d = self.preview()[0].data
        self.assertEqual((d["recommended_size"], d["compatibility"]), (None, None))

    def test_another_users_avatar_is_a_404(self):
        foreign = self.make_avatar(user=self.other, is_default=False)
        self.assertEqual(self.preview(avatar=str(foreign.pk))[0].status_code, 404)

    def test_unknown_category_is_reported_and_can_be_chosen(self):
        html = page(title="Mystery Garment")
        d = self.preview(html, url="https://shop.example/item/1")[0].data
        self.assertEqual((d["category"], d["needs_category"]), (None, True))
        d = self.preview(html, url="https://shop.example/item/1", category="hoodies")[0].data
        self.assertEqual((d["category"], d["needs_category"]), ("hoodies", False))

    def test_a_page_without_a_chart_gets_the_generic_one_and_is_approximate(self):
        d = self.preview(page(title="Soft Hoodie", sizes=False))[0].data
        self.assertEqual((d["size_chart_source"], d["approximate"], d["category"]), ("default", True, "hoodies"))
        self.assertEqual(d["size_range"], "XS–6XL")

    def test_the_template_database_is_used_when_the_page_has_no_chart(self):
        tpl = self.make_product(title="Slim Fit Jeans", slug="jeans")
        Brand.objects.filter(pk=tpl.brand_id).update(name="DenimCo")
        Product.objects.filter(pk=tpl.pk).update(is_template=True)
        d = self.preview(page(sizes=False))[0].data
        self.assertEqual((d["source"], d["product_id"], d["already_in_catalog"], d["approximate"]), ("template", tpl.pk, True, False))

    def test_an_already_imported_link_is_not_downloaded_again(self):
        first, _ = self.preview()
        self.confirm(preview_token=first.data["preview_token"])
        r, fetch = self.preview()
        self.assertEqual((r.data["source"], r.data["already_in_catalog"]), ("existing", True))
        fetch.assert_not_called()

    def test_input_errors(self):
        self.assertEqual(self.client.post(reverse("product-import-preview"), {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(reverse("product-import-preview"), {"url": "nope"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(reverse("product-import-preview"), {"preview_token": "x"}, format="json").status_code, 400)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(reverse("product-import-preview"), {"url": URL}, format="json").status_code, 401)


class ConfirmTests(ImportBase):
    def test_confirm_adds_exactly_what_was_previewed_without_downloading_again(self):
        self.make_avatar()
        token = self.preview()[0].data["preview_token"]
        r = self.confirm(preview_token=token)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["title"], r.data["price"], r.data["category"], r.data["brand"]),
                         ("Slim Fit Jeans", 1450.0, "jeans", "DenimCo"))
        self.assertEqual([s["label"] for s in r.data["sizes"]], ["30", "32"])
        self.assertEqual((r.data["recommended_size"], r.data["compatibility"]), ("32", 100))
        product = Product.objects.get()
        self.assertEqual((product.owner, product.source_url), (self.user, URL))

    def test_confirming_twice_returns_the_same_product(self):
        token = self.preview()[0].data["preview_token"]
        a = self.confirm(preview_token=token)
        b = self.confirm(preview_token=token)
        self.assertEqual((a.status_code, b.status_code, a.data["id"]), (201, 200, b.data["id"]))
        self.assertEqual(Product.objects.count(), 1)

    def test_bad_tokens_are_rejected(self):
        token = self.preview()[0].data["preview_token"]
        for bad in ("garbage", token[:-3] + "abc", token + "x"):
            r = self.confirm(preview_token=bad)
            self.assertEqual((r.status_code, r.data["code"]), (400, "invalid_preview"), bad)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.confirm(preview_token=token).data["code"], "invalid_preview")
        self.assertEqual(Product.objects.count(), 0)

    def test_an_expired_preview_is_rejected(self):
        token = self.preview()[0].data["preview_token"]
        with mock.patch("catalog.importflow.TOKEN_TTL", -1):
            self.assertEqual(self.confirm(preview_token=token).data["code"], "invalid_preview")

    def test_a_forged_payload_cannot_inject_other_data(self):
        forged = signing.dumps({"u": self.user.pk, "d": {"title": "x"}}, salt="other.salt", compress=True)
        self.assertEqual(self.confirm(preview_token=forged).data["code"], "invalid_preview")

    def test_the_category_can_be_chosen_at_confirmation(self):
        html = page(title="Mystery Garment")
        token = self.preview(html, url="https://shop.example/item/1")[0].data["preview_token"]
        r = self.confirm(preview_token=token)
        self.assertEqual((r.status_code, "category" in r.data), (400, True))
        r = self.confirm(preview_token=token, category="hoodies", gender="female")
        self.assertEqual((r.status_code, r.data["category"], r.data["gender"]), (201, "hoodies", "female"))

    def test_confirming_a_template_match_returns_the_template(self):
        tpl = self.make_product(title="Slim Fit Jeans", slug="jeans")
        Brand.objects.filter(pk=tpl.brand_id).update(name="DenimCo")
        Product.objects.filter(pk=tpl.pk).update(is_template=True)
        token = self.preview(page(sizes=False))[0].data["preview_token"]
        r = self.confirm(preview_token=token)
        self.assertEqual((r.status_code, r.data["id"], r.data["is_template"]), (200, tpl.pk, True))
        self.assertEqual(Product.objects.count(), 1)

    def test_a_generic_chart_product_is_marked_approximate(self):
        token = self.preview(page(title="Soft Hoodie", sizes=False))[0].data["preview_token"]
        r = self.confirm(preview_token=token)
        self.assertEqual((r.status_code, r.data["approximate"], r.data["size_chart_source"]), (201, True, "default"))

    def test_the_one_step_import_still_works(self):
        with mock.patch("catalog.views.fetch_html", return_value=page()):
            r = self.client.post(reverse("product-import"), {"url": URL}, format="json")
        self.assertEqual((r.status_code, r.data["title"]), (201, "Slim Fit Jeans"))

    def test_the_imported_product_is_private_to_the_user(self):
        token = self.preview()[0].data["preview_token"]
        pid = self.confirm(preview_token=token).data["id"]
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("product-detail", args=[pid])).status_code, 404)


class ErrorCodeTests(ImportBase):
    def failing(self, code, url=URL):
        with mock.patch("catalog.views.fetch_html", side_effect=PageImportError(code, "x")):
            return self.client.post(reverse("product-import-preview"), {"url": url}, format="json")

    def test_blocked_shop_tells_the_app_to_offer_the_catalog(self):
        r = self.failing("blocked_by_site", "https://shop.example/ua/men/hoodie-oversize-p9/")
        self.assertEqual((r.status_code, r.data["code"], r.data["suggestion"], r.data["category"]),
                         (422, "blocked_by_site", "choose_from_catalog", "hoodies"))

    def test_other_recoverable_errors_carry_the_suggestion_too(self):
        for code in ("timeout", "not_found", "fetch_failed", "size_chart_not_found", "too_large", "unresolvable"):
            r = self.failing(code, "https://shop.example/p/1")
            self.assertEqual((r.status_code, r.data["code"], r.data["suggestion"]), (422, code, "choose_from_catalog"))
            self.assertNotIn("category", r.data)

    def test_unfixable_input_gets_no_suggestion(self):
        for code in ("invalid_url", "forbidden_host"):
            self.assertNotIn("suggestion", self.failing(code).data)

    def test_the_same_codes_come_from_the_one_step_import(self):
        with mock.patch("catalog.views.fetch_html", side_effect=PageImportError("blocked_by_site", "x")):
            r = self.client.post(reverse("product-import"), {"url": URL}, format="json")
        self.assertEqual((r.status_code, r.data["code"]), (422, "blocked_by_site"))


def fake_response(status=200, body=b"<html></html>", redirect=None):
    resp = mock.Mock(status_code=status, is_redirect=bool(redirect), encoding="utf-8")
    resp.headers = {"Location": redirect} if redirect else {}
    resp.raw.read.return_value = body
    return resp


def public_dns(host, port):
    return [(2, 1, 6, "", ("93.184.216.34", port))]


class FetchHardeningTests(ImportBase):
    def fetch(self, resp=None, exc=None):
        patches = [mock.patch("catalog.importers.socket.getaddrinfo", side_effect=public_dns)]
        patches.append(mock.patch("catalog.importers.requests.get", side_effect=exc) if exc
                       else mock.patch("catalog.importers.requests.get", return_value=resp))
        with patches[0], patches[1]:
            return fetch_html("https://shop.example/p/1")

    def code(self, **kw):
        with self.assertRaises(PageImportError) as ctx:
            self.fetch(**kw)
        return ctx.exception.code

    def test_status_codes_map_to_clear_error_codes(self):
        for status, code in ((401, "blocked_by_site"), (403, "blocked_by_site"), (429, "blocked_by_site"),
                             (503, "blocked_by_site"), (404, "not_found"), (410, "not_found"), (500, "fetch_failed"),
                             (400, "fetch_failed")):
            self.assertEqual(self.code(resp=fake_response(status)), code, status)

    def test_timeouts_and_connection_errors(self):
        self.assertEqual(self.code(exc=requests.Timeout()), "timeout")
        self.assertEqual(self.code(exc=requests.ConnectionError()), "fetch_failed")

    def test_a_challenge_page_with_http_200_counts_as_blocked(self):
        for body in (b"<html><title>Just a moment...</title></html>", b"<div>Please solve the CAPTCHA</div>",
                     b"<h1>Access Denied</h1>", b"<p>Verify you are human</p>"):
            self.assertEqual(self.code(resp=fake_response(200, body)), "blocked_by_site", body)

    def test_a_real_product_page_that_mentions_captcha_is_fine(self):
        body = (page() + "<footer>This form is protected by reCAPTCHA</footer>").encode()
        self.assertIn("Slim Fit Jeans", self.fetch(resp=fake_response(200, body)))
        table_only = b"<table><tr><th>Size</th></tr></table><footer>captcha</footer>"
        self.assertIn("<table", self.fetch(resp=fake_response(200, table_only)))

    def test_an_ordinary_page_passes_through(self):
        self.assertEqual(self.fetch(resp=fake_response(200, b"<html>hello</html>")), "<html>hello</html>")


class CategoryGuessTests(ImportBase):
    def test_real_garments_are_recognised(self):
        cases = {"Slim-fit Jeans": "jeans", "Oversized Hoodie": "hoodies", "Summer Dress": "dresses",
                 "Базова футболка": "tshirts", "Плаття міді": "dresses", "Худі оверсайз": "hoodies",
                 "T-Shirt basic": "tshirts", "Classic Tee": "tshirts", "Джинси прямі": "jeans",
                 "/ua/men/hoodie-oversize-p123": "hoodies", "Світшот": "hoodies", "Denim jacket": "jeans"}
        for text, slug in cases.items():
            self.assertEqual(guess_category_slug(text), slug, text)

    def test_look_alike_words_are_not_misread(self):
        for text in ("Steel bottle", "Streetwear jacket", "Платформа", "Dressing gown", "Platinum ring",
                     "Teenage backpack", "Coat", "", None):
            self.assertIsNone(guess_category_slug(text), text)


class AdapterTests(ImportBase):
    def tearDown(self):
        importers.ADAPTERS.pop("fakeshop.example", None)
        importers.ADAPTERS.pop("zara.com", None)

    def test_a_registered_adapter_is_used_for_its_domain_and_subdomains(self):
        calls = []

        def adapter(html, url):
            calls.append(url)
            return {"title": "From adapter", "brand": "Fake", "image_url": "", "sizes": [], "price": None, "currency": "UAH"}

        register_adapter("fakeshop.example", adapter)
        for url in ("https://fakeshop.example/p/1", "https://www.fakeshop.example/p/2", "https://m.fakeshop.example/x"):
            self.assertEqual(parse_product_page("<html></html>", url)["title"], "From adapter")
        self.assertEqual(len(calls), 3)
        self.assertNotEqual(parse_product_page(page(), "https://otherfakeshop.example/p")["title"], "From adapter")
        self.assertNotEqual(parse_product_page(page(), "https://fakeshop.example.evil.com/p")["title"], "From adapter")

    def test_an_adapter_may_decline_and_the_universal_parser_takes_over(self):
        register_adapter("fakeshop.example", lambda html, url: None)
        self.assertEqual(parse_product_page(page(), "https://fakeshop.example/p")["title"], "Slim Fit Jeans")

    def test_without_a_url_only_the_universal_parser_runs(self):
        register_adapter("fakeshop.example", lambda html, url: {"title": "no"})
        self.assertEqual(parse_product_page(page())["title"], "Slim Fit Jeans")

    def test_the_adapter_receives_the_preview_flow(self):
        register_adapter("fakeshop.example", lambda html, url: {
            "title": "Adapter Hoodie", "brand": "Fake", "image_url": "", "price": None, "currency": "UAH",
            "sizes": [{"label": "M", "order": 0, "chest_min": 92.0, "chest_max": 100.0}]})
        r, _ = self.preview(html="<html></html>", url="https://fakeshop.example/hoodie/1")
        self.assertEqual((r.data["title"], r.data["category"], r.data["size_range"]), ("Adapter Hoodie", "hoodies", "M"))


class ShopListTests(ImportBase):
    def test_listed_shops_and_their_mode(self):
        r = self.client.get(reverse("import-shops"))
        self.assertEqual([s["name"] for s in r.data["shops"]], ["Rozetka", "Zara", "H&M", "ASOS"])
        self.assertEqual({s["mode"] for s in r.data["shops"]}, {"universal"})
        register_adapter("zara.com", lambda html, url: None)
        try:
            modes = {s["name"]: s["mode"] for s in listed_shops()}
            self.assertEqual((modes["Zara"], modes["H&M"]), ("adapter", "universal"))
        finally:
            importers.ADAPTERS.pop("zara.com", None)

    def test_shop_name_from_a_link(self):
        self.assertEqual(shop_for("https://www.rozetka.com.ua/p/1")["name"], "Rozetka")
        self.assertEqual(shop_for("https://m.hm.com/x")["name"], "H&M")
        self.assertEqual(shop_for("https://www2.asos.com/y")["name"], "ASOS")
        self.assertEqual(shop_for("https://www.shop.example/x"), {"name": "shop.example", "domain": "shop.example"})
        self.assertEqual(shop_for("https://notrozetka.com.ua/x")["name"], "notrozetka.com.ua")

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("import-shops")).status_code, 401)


class SimilarProductsTests(ImportBase):
    def setUp(self):
        super().setUp()
        self.make_avatar()
        self.base = self.make_product(title="Base", slug="hoodies")
        self.near = self.make_product(title="Near", slug="hoodies")
        self.loose = self.make_product(title="Loose", slug="hoodies", chart={"L": ((100, 108), (86, 94), (102, 110))})
        self.huge = self.make_product(title="Huge", slug="hoodies", chart={"XXL": ((130, 140), (120, 130), (130, 140))})
        self.her = self.make_product(title="Hers", slug="hoodies", gender="female")
        self.other_cat = self.make_product(title="Tee", slug="tshirts")
        self.theirs = self.make_product(title="Theirs", slug="hoodies", owner=self.other)

    def similar(self, product=None, **params):
        return self.client.get(reverse("product-similar", args=[(product or self.base).pk]), params)

    def test_same_category_fitting_best_first_and_never_the_product_itself(self):
        r = self.similar()
        self.assertEqual(r.status_code, 200, r.data)
        titles = [p["title"] for p in r.data]
        self.assertEqual(titles, ["Near", "Loose"])
        scores = [p["compatibility"] for p in r.data]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertNotIn("Base", titles)
        self.assertTrue(all(p["recommended_size"] for p in r.data))

    def test_without_personalisation_everything_visible_in_the_category_appears(self):
        titles = {p["title"] for p in self.similar(personalized="false").data}
        self.assertEqual(titles, {"Near", "Loose", "Huge", "Hers"})
        self.assertNotIn("Theirs", titles)

    def test_a_gendered_base_product_keeps_to_its_gender_and_unisex(self):
        mens = self.make_product(title="Mens", slug="hoodies", gender="male")
        titles = {p["title"] for p in self.similar(mens, personalized="false").data}
        self.assertNotIn("Hers", titles)
        self.assertIn("Near", titles)

    def test_limit_and_validation(self):
        for i in range(5):
            self.make_product(title=f"More {i}", slug="hoodies")
        self.assertEqual(len(self.similar(limit=3).data), 3)
        for bad in (0, 21, "x"):
            self.assertEqual(self.similar(limit=bad).status_code, 400, bad)

    def test_no_avatar_still_works_without_compatibility(self):
        self.client.force_authenticate(self.other)
        r = self.similar(self.near)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(p["compatibility"] is None for p in r.data))

    def test_unknown_or_private_products_and_foreign_avatars(self):
        self.assertEqual(self.client.get(reverse("product-similar", args=[999999])).status_code, 404)
        self.assertEqual(self.similar(self.theirs).status_code, 404)
        foreign = self.make_avatar(user=self.other, is_default=False)
        self.assertEqual(self.similar(avatar=str(foreign.pk)).status_code, 404)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.similar().status_code, 401)