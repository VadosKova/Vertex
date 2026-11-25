from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User

from .measurements import SPEC, estimate_missing, validate_measurements
from .models import Avatar

PASSWORD = "S3cure-pass-word"
CORE = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}


class BaseTest(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice", gender="female")
        self.other = User.objects.create_user("bob@example.com", PASSWORD, username="Bob", gender="male")
        self.client.force_authenticate(self.user)

    def payload(self, **over):
        data = {"name": "Me", "gender": "female", "age": 25, "height_cm": 170, "weight_kg": 60,
                "body_type": "mesomorph", "measurements": dict(CORE)}
        data.update(over)
        return data

    def make(self, user=None, **over):
        base = dict(user=user or self.user, name="Me", gender="female", age=25, height_cm=170, weight_kg=60,
                    measurements=dict(CORE))
        base.update(over)
        return Avatar.objects.create(**base)


class MeasurementRulesTests(BaseTest):
    def test_spec_covers_all_fields_from_tz_plus_eu_foot_size(self):
        self.assertEqual(len(SPEC), 25)
        r = self.client.get(reverse("measurement-spec"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({x["key"] for x in r.data}, set(SPEC))
        self.assertIn("uk", r.data[0]["hint"])

    def test_range_and_cross_field_validation(self):
        self.assertTrue(validate_measurements({"waist_circumference": 500}))
        self.assertTrue(validate_measurements({"nonsense": 1}))
        self.assertTrue(validate_measurements({"chest_circumference": "big"}))
        self.assertTrue(validate_measurements({"bicep_relaxed": 40, "bicep_flexed": 30}))
        self.assertTrue(validate_measurements({"inseam": 90, "outseam": 85}))
        self.assertEqual(validate_measurements({"chest_circumference": 96, "underbust_circumference": 80}), {})

    def test_estimate_missing_flags_estimated_fields(self):
        full, est = estimate_missing(180, "male", {"inseam": 82})
        self.assertNotIn("inseam", est)
        self.assertIn("shoulder_width", est)
        self.assertAlmostEqual(full["shoulder_width"], 46.6, places=1)


class AvatarCrudTests(BaseTest):
    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("avatar-list")).status_code, 401)

    def test_create_first_becomes_default_second_does_not(self):
        r = self.client.post(reverse("avatar-list"), self.payload(), format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["is_default"])
        self.assertIn("shoulder_width", r.data["estimated_fields"])
        r2 = self.client.post(reverse("avatar-list"), self.payload(name="Second"), format="json")
        self.assertFalse(r2.data["is_default"])

    def test_name_and_gender_default_to_account_values(self):
        p = self.payload()
        del p["name"], p["gender"]
        r = self.client.post(reverse("avatar-list"), p, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["name"], r.data["gender"]), ("Alice", "female"))

    def test_gender_required_if_account_has_none(self):
        User.objects.filter(pk=self.user.pk).update(gender="")
        self.user.refresh_from_db()
        p = self.payload()
        del p["gender"]
        r = self.client.post(reverse("avatar-list"), p, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("gender", r.data)

    def test_required_core_measurements(self):
        r = self.client.post(reverse("avatar-list"), self.payload(measurements={"chest_circumference": 96}), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("waist_circumference", r.data["measurements"])
        self.assertIn("hip_circumference", r.data["measurements"])

    def test_rejects_out_of_range_values_and_implausible_bmi(self):
        url = reverse("avatar-list")
        self.assertEqual(self.client.post(url, self.payload(height_cm=50), format="json").status_code, 400)
        self.assertEqual(self.client.post(url, self.payload(age=5), format="json").status_code, 400)
        self.assertEqual(self.client.post(url, self.payload(gender="x"), format="json").status_code, 400)
        r = self.client.post(url, self.payload(height_cm=190, weight_kg=31), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("weight_kg", r.data)
        bad = dict(CORE, waist_circumference=500)
        self.assertEqual(self.client.post(url, self.payload(measurements=bad), format="json").status_code, 400)

    def test_measurements_update_bumps_timestamp_other_fields_do_not(self):
        a = self.make()
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=timezone.now() - timezone.timedelta(days=40))
        a.refresh_from_db()
        old = a.measurements_updated_at
        self.client.patch(reverse("avatar-detail", args=[a.pk]), {"name": "Renamed"}, format="json")
        a.refresh_from_db()
        self.assertEqual(a.measurements_updated_at, old)
        m = dict(a.measurements, waist_circumference=90)
        r = self.client.patch(reverse("avatar-detail", args=[a.pk]), {"measurements": m}, format="json")
        self.assertEqual(r.status_code, 200)
        a.refresh_from_db()
        self.assertGreater(a.measurements_updated_at, old)

    def test_partial_update_keeps_validation(self):
        a = self.make()
        r = self.client.patch(reverse("avatar-detail", args=[a.pk]), {"height_cm": 300}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.patch(reverse("avatar-detail", args=[a.pk]), {"weight_kg": 25}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_set_default_switches_flag(self):
        a1 = self.make(is_default=True)
        a2 = self.make(name="B")
        r = self.client.post(reverse("avatar-set-default", args=[a2.pk]))
        self.assertEqual(r.status_code, 200)
        a1.refresh_from_db(); a2.refresh_from_db()
        self.assertEqual((a1.is_default, a2.is_default), (False, True))

    def test_database_allows_only_one_default_per_user(self):
        self.make(is_default=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make(is_default=True)

    def test_deleting_default_promotes_another(self):
        a1 = self.make(is_default=True)
        a2 = self.make(name="B")
        self.assertEqual(self.client.delete(reverse("avatar-detail", args=[a1.pk])).status_code, 204)
        a2.refresh_from_db()
        self.assertTrue(a2.is_default)

    def test_users_cannot_access_each_others_avatars(self):
        theirs = self.make(user=self.other, gender="male")
        url = reverse("avatar-detail", args=[theirs.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"name": "hack"}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(self.client.post(reverse("avatar-set-default", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("avatar-list")).data, [])


class DraftTests(BaseTest):
    def test_draft_roundtrip_and_cleared_on_avatar_create(self):
        self.assertIsNone(self.client.get(reverse("avatar-draft")).data["payload"])
        r = self.client.put(reverse("avatar-draft"), {"payload": {"height_cm": 181, "step": 2}}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("avatar-draft")).data["payload"]["height_cm"], 181)
        self.client.put(reverse("avatar-draft"), {"payload": {"height_cm": 182}}, format="json")
        self.assertEqual(self.client.get(reverse("avatar-draft")).data["payload"], {"height_cm": 182})
        self.client.post(reverse("avatar-list"), self.payload(), format="json")
        self.assertIsNone(self.client.get(reverse("avatar-draft")).data["payload"])

    def test_draft_validation_delete_and_isolation(self):
        self.assertEqual(self.client.put(reverse("avatar-draft"), {"payload": "str"}, format="json").status_code, 400)
        self.client.put(reverse("avatar-draft"), {"payload": {"a": 1}}, format="json")
        self.client.force_authenticate(self.other)
        self.assertIsNone(self.client.get(reverse("avatar-draft")).data["payload"])
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(reverse("avatar-draft")).status_code, 204)
        self.assertIsNone(self.client.get(reverse("avatar-draft")).data["payload"])


# --photos--
import io
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4
from unittest import mock

import numpy as np
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image, ImageFilter

from .models import AvatarPhoto
from .services.photo_quality import assess

_TMP = Path(tempfile.mkdtemp(prefix="vertex-test-media-"))


def make_photo(kind="sharp", size=(640, 640), fmt="JPEG", exif=None, name=None):
    rng = np.random.default_rng(1)
    w, h = size
    if kind == "pattern":
        yy, xx = np.indices((h, w))
        board = (((xx // 4) + (yy // 4)) % 2) * 160 + 40
        arr = np.repeat(board[:, :, None], 3, axis=2).astype(np.uint8)
    elif kind == "dark":
        arr = rng.integers(0, 40, (h, w, 3), dtype=np.uint8)
    elif kind == "bright":
        arr = rng.integers(225, 256, (h, w, 3), dtype=np.uint8)
    else:
        arr = rng.integers(0, 256, (h, w, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    if kind == "blurry":
        img = img.filter(ImageFilter.GaussianBlur(25))
    buf = io.BytesIO()
    kwargs = {"exif": exif} if exif else {}
    img.save(buf, fmt, **kwargs)
    return SimpleUploadedFile(name or f"photo.{fmt.lower()}", buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=_TMP, FILE_ENCRYPTION_KEY=Fernet.generate_key().decode())
class PhotoTests(BaseTest):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP, ignore_errors=True)

    def upload(self, avatar, f=None, **extra):
        return self.client.post(reverse("avatar-photos", args=[avatar.pk]), {"image": f or make_photo(), **extra},
                                format="multipart")

    def stored(self, photo_id):
        return AvatarPhoto.objects.get(pk=photo_id)

    def test_assess_detects_each_problem(self):
        opened = lambda f: Image.open(io.BytesIO(f.read()))
        self.assertTrue(assess(opened(make_photo("sharp")))["ok"])
        self.assertIn("blurry", assess(opened(make_photo("blurry")))["issues"])
        self.assertIn("too_dark", assess(opened(make_photo("dark")))["issues"])
        self.assertIn("too_bright", assess(opened(make_photo("bright")))["issues"])
        self.assertIn("too_small", assess(opened(make_photo("sharp", size=(200, 200))))["issues"])

    def test_good_photo_is_encrypted_on_disk_and_readable_only_by_owner(self):
        a = self.make()
        r = self.upload(a, kind="front")
        self.assertEqual(r.status_code, 201, r.data)
        photo = self.stored(r.data["id"])
        self.assertTrue(photo.file.path.startswith(str(_TMP)))
        raw = Path(photo.file.path).read_bytes()
        self.assertFalse(raw.startswith(b"\xff\xd8"), "photo must not be a plaintext JPEG on disk")
        got = self.client.get(reverse("avatar-photo-detail", args=[a.pk, photo.pk]))
        self.assertEqual((got.status_code, got["Content-Type"]), (200, "image/jpeg"))
        self.assertTrue(got.content.startswith(b"\xff\xd8"))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(reverse("avatar-photo-detail", args=[a.pk, photo.pk])).status_code, 404)

    def test_photo_listed_in_avatar_detail(self):
        a = self.make()
        pid = self.upload(a).data["id"]
        photos = self.client.get(reverse("avatar-detail", args=[a.pk])).data["photos"]
        self.assertEqual([p["id"] for p in photos], [pid])

    def test_the_photo_size_limit_has_a_default_when_the_setting_is_missing(self):
        from django.conf import settings
        a = self.make()
        with override_settings():
            del settings.MAX_PHOTO_BYTES
            self.assertEqual(self.upload(a).status_code, 201)

    def test_bad_quality_returns_422_with_issue_codes_and_saves_nothing(self):
        a = self.make()
        for kind, issue in (("blurry", "blurry"), ("dark", "too_dark"), ("bright", "too_bright")):
            r = self.upload(a, make_photo(kind))
            self.assertEqual(r.status_code, 422, kind)
            self.assertIn(issue, r.data["issues"])
        self.assertEqual(a.photos.count(), 0)

    def test_rejects_non_images_and_unsupported_formats(self):
        a = self.make()
        junk = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        self.assertEqual(self.upload(a, junk).status_code, 400)
        buf = io.BytesIO(); Image.new("RGB", (600, 600)).save(buf, "GIF")
        gif = SimpleUploadedFile("x.gif", buf.getvalue(), content_type="image/gif")
        self.assertEqual(self.upload(a, gif).status_code, 400)
        self.assertEqual(self.client.post(reverse("avatar-photos", args=[a.pk]), {}, format="multipart").status_code, 400)
        self.assertEqual(self.upload(a, kind="selfie").status_code, 400)

    def test_rejects_huge_resolution_before_decoding(self):
        a = self.make()
        with mock.patch("avatars.services.photo_processing.MAX_PIXELS", 100_000):
            self.assertEqual(self.upload(a, make_photo(size=(640, 640))).status_code, 400)

    def test_rejects_oversized_file(self):
        a = self.make()
        with override_settings(MAX_PHOTO_BYTES=1000):
            self.assertEqual(self.upload(a).status_code, 413)

    def test_three_kinds_one_photo_each_and_a_new_upload_replaces_the_old(self):
        a = self.make()
        ids = {}
        for kind in ("front", "profile_left", "profile_right"):
            r = self.upload(a, make_photo(), kind=kind)
            self.assertEqual(r.status_code, 201, (kind, r.data))
            ids[kind] = r.data["id"]
        self.assertEqual(a.photos.count(), 3)
        old_path = Path(AvatarPhoto.objects.get(pk=ids["front"]).file.path)
        self.assertTrue(old_path.exists())
        again = self.upload(a, make_photo(), kind="front")
        self.assertEqual(again.status_code, 201)
        self.assertEqual(a.photos.count(), 3)
        self.assertFalse(AvatarPhoto.objects.filter(pk=ids["front"]).exists())
        self.assertFalse(old_path.exists())
        detail = self.client.get(reverse("avatar-detail", args=[a.pk])).data
        self.assertEqual(sorted(p["kind"] for p in detail["photos"]), ["front", "profile_left", "profile_right"])
        self.assertTrue(detail["has_front_photo"])

    def test_legacy_kind_and_unknown_kinds_are_rejected(self):
        a = self.make()
        for kind in ("profile", "selfie", "FRONT"):
            self.assertEqual(self.upload(a, make_photo(), kind=kind).status_code, 400, kind)

    def test_metadata_is_stripped_and_orientation_applied(self):
        a = self.make()
        exif = Image.Exif()
        exif[0x010F] = "SecretCameraMaker"
        exif[0x0112] = 6
        r = self.upload(a, make_photo(size=(800, 640), exif=exif.tobytes()))
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual((r.data["quality"]["width"], r.data["quality"]["height"]), (640, 800))
        with self.stored(r.data["id"]).file.open("rb") as fh:
            saved = Image.open(io.BytesIO(fh.read()))
        self.assertEqual(saved.size, (640, 800))
        self.assertNotIn(0x010F, saved.getexif())

    def test_png_is_converted_and_big_images_are_downscaled(self):
        a = self.make()
        r = self.upload(a, make_photo("pattern", size=(2400, 2000), fmt="PNG"))
        self.assertEqual(r.status_code, 201, r.data)
        with self.stored(r.data["id"]).file.open("rb") as fh:
            saved = Image.open(io.BytesIO(fh.read()))
        self.assertEqual(saved.format, "JPEG")
        self.assertLessEqual(max(saved.size), 1600)

    def test_cannot_upload_to_or_read_from_another_users_avatar(self):
        theirs = self.make(user=self.other, gender="male")
        self.assertEqual(self.upload(theirs).status_code, 404)

    def test_files_are_removed_from_disk_on_photo_avatar_and_account_deletion(self):
        a = self.make()
        p1 = self.stored(self.upload(a).data["id"]); path1 = Path(p1.file.path)
        self.assertTrue(path1.exists())
        self.assertEqual(self.client.delete(reverse("avatar-photo-detail", args=[a.pk, p1.pk])).status_code, 204)
        self.assertFalse(path1.exists())
        p2 = self.stored(self.upload(a).data["id"]); path2 = Path(p2.file.path)
        self.client.delete(reverse("avatar-detail", args=[a.pk]))
        self.assertFalse(path2.exists())
        a2 = self.make(name="again")
        p3 = self.stored(self.upload(a2).data["id"]); path3 = Path(p3.file.path)
        self.client.delete(reverse("me"))
        self.assertFalse(path3.exists())

    def test_wrong_key_cannot_decrypt(self):
        a = self.make()
        photo = self.stored(self.upload(a).data["id"])
        with override_settings(FILE_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(Exception):
                photo.file.open("rb")


# --3D generation--
import json
import struct

from .services.generator import compute_morph_params


def read_glb(data: bytes):
    magic, version, length = struct.unpack("<4sII", data[:12])
    jlen, jtype = struct.unpack("<I4s", data[12:20])
    doc = json.loads(data[20:20 + jlen])
    off = 20 + jlen
    blen, btype = struct.unpack("<I4s", data[off:off + 8])
    return (magic, version, length), doc, (jtype, btype), data[off + 8:off + 8 + blen]


@override_settings(MEDIA_ROOT=_TMP, FILE_ENCRYPTION_KEY=Fernet.generate_key().decode(), AVATAR_GENERATION_EAGER=True)
class GenerationTests(BaseTest):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP, ignore_errors=True)

    def make(self, user=None, photo=True, **over):
        avatar = super().make(user=user, **over)
        if photo:
            self.add_photo(avatar)
        return avatar

    def add_photo(self, avatar, kind="front"):
        from django.core.files.base import ContentFile
        p = AvatarPhoto(avatar=avatar, kind=kind, quality={"ok": True})
        p.file.save(f"{p.pk}.jpg", ContentFile(make_photo().read()), save=False)
        p.save()
        return p

    def generate(self, a):
        return self.client.post(reverse("avatar-generate", args=[a.pk]))

    def status(self, a):
        return self.client.get(reverse("avatar-generation-status", args=[a.pk])).data

    def test_generation_produces_valid_glb_and_ready_status(self):
        a = self.make(height_cm=180, gender="male")
        r = self.generate(a)
        self.assertEqual(r.status_code, 202, r.data)
        st = self.status(a)
        self.assertEqual((st["status"], st["stage"], st["progress"], st["needs_regeneration"]), ("ready", "done", 100, False))
        resp = self.client.get(reverse("avatar-model", args=[a.pk]))
        self.assertEqual((resp.status_code, resp["Content-Type"]), (200, "model/gltf-binary"))
        self.assertIn("private", resp["Cache-Control"])
        data = b"".join(resp.streaming_content)
        (magic, version, length), doc, (jtype, btype), binary = read_glb(data)
        self.assertEqual((magic, version, length), (b"glTF", 2, len(data)))
        self.assertEqual((jtype, btype), (b"JSON", b"BIN\x00"))
        self.assertEqual(doc["buffers"][0]["byteLength"], len(binary))
        self.assertAlmostEqual(doc["accessors"][0]["max"][1], 1.8, places=2)
        self.assertIn("waist", doc["nodes"][0]["extras"]["morph"])
        self.assertEqual({x["state"] for x in st["stages"]}, {"done"})
        self.assertEqual([x["key"] for x in st["stages"]],
                         ["body_analysis", "face_mesh", "body_mesh", "skin_texture", "finalize"])
        self.assertIsNotNone(st["generation_seconds"])

    def test_response_exposes_model_url_only_when_ready(self):
        a = self.make()
        self.assertIsNone(self.client.get(reverse("avatar-detail", args=[a.pk])).data["model_url"])
        self.generate(a)
        data = self.client.get(reverse("avatar-detail", args=[a.pk])).data
        self.assertTrue(data["model_url"].endswith(f"/api/v1/avatars/{a.pk}/model/"))
        self.assertIn("waist", data["morph_params"])

    def test_photo_is_analysed_during_generation(self):
        a = self.make()
        self.client.post(reverse("avatar-photos", args=[a.pk]), {"image": make_photo()}, format="multipart")
        self.generate(a)
        a.refresh_from_db()
        self.assertEqual(a.face_data["engine"], "basic")
        self.assertEqual(len(a.face_data["skin_rgb"]), 3)

    def test_morph_params_reflect_body_shape(self):
        slim = self.make(gender="male", height_cm=180, measurements={"chest_circumference": 80, "waist_circumference": 66, "hip_circumference": 88})
        wide = self.make(gender="male", height_cm=180, weight_kg=110, measurements={"chest_circumference": 115, "waist_circumference": 105, "hip_circumference": 115})
        s, w = compute_morph_params(slim), compute_morph_params(wide)
        self.assertLess(s["waist"], 0)
        self.assertGreater(w["waist"], s["waist"])
        self.assertTrue(all(-0.5 <= w[k] <= 0.5 for k in ("chest", "waist", "hips", "shoulders")))
        self.assertGreater(w["bmi"], s["bmi"])

    def test_model_flag_goes_stale_after_edits_and_photos(self):
        a = self.make()
        self.generate(a)
        self.assertFalse(self.status(a)["needs_regeneration"])
        self.client.patch(reverse("avatar-detail", args=[a.pk]), {"name": "Renamed"}, format="json")
        self.assertFalse(self.status(a)["needs_regeneration"])
        self.client.patch(reverse("avatar-detail", args=[a.pk]), {"weight_kg": 70}, format="json")
        self.assertTrue(self.status(a)["needs_regeneration"])
        self.generate(a)
        self.client.post(reverse("avatar-photos", args=[a.pk]), {"image": make_photo()}, format="multipart")
        self.assertTrue(self.status(a)["needs_regeneration"])

    def test_regeneration_replaces_the_old_file(self):
        a = self.make()
        self.generate(a)
        a.refresh_from_db()
        first = Path(a.model_file.path)
        self.assertTrue(first.exists())
        self.client.patch(reverse("avatar-detail", args=[a.pk]), {"height_cm": 175}, format="json")
        self.generate(a)
        a.refresh_from_db()
        files = list((_TMP / "avatars").glob(f"{a.pk}*"))
        self.assertEqual(len(files), 1)
        self.assertFalse(first.exists() and first != Path(a.model_file.path))

    def test_model_not_available_until_ready(self):
        a = self.make()
        self.assertEqual(self.client.get(reverse("avatar-model", args=[a.pk])).status_code, 404)

    def test_concurrent_generation_is_refused_but_stale_jobs_can_restart(self):
        a = self.make()
        Avatar.objects.filter(pk=a.pk).update(status="processing", processing_started_at=timezone.now())
        self.assertEqual(self.generate(a).status_code, 409)
        Avatar.objects.filter(pk=a.pk).update(processing_started_at=timezone.now() - timezone.timedelta(minutes=10))
        self.assertEqual(self.generate(a).status_code, 202)
        self.assertEqual(self.status(a)["status"], "ready")

    def test_failure_is_reported_and_retry_works(self):
        a = self.make()
        with mock.patch("avatars.services.generator.compute_morph_params", side_effect=RuntimeError("boom")), \
                self.assertLogs("avatars.services.generator", level="ERROR"):
            self.generate(a)
        st = self.status(a)
        self.assertEqual((st["status"], st["stage"]), ("failed", "body_analysis"))
        self.assertEqual([x["state"] for x in st["stages"]], ["failed", "pending", "pending", "pending", "pending"])
        self.assertIn("boom", st["error"])
        self.generate(a)
        self.assertEqual(self.status(a)["status"], "ready")
        self.assertEqual(self.status(a)["error"], "")

    def test_generation_endpoints_are_private(self):
        theirs = self.make(user=self.other, gender="male")
        self.assertEqual(self.generate(theirs).status_code, 404)
        self.assertEqual(self.client.get(reverse("avatar-generation-status", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("avatar-model", args=[theirs.pk])).status_code, 404)

    def test_requires_login(self):
        a = self.make()
        self.client.force_authenticate(None)
        self.assertEqual(self.generate(a).status_code, 401)

    def test_model_file_is_deleted_with_the_avatar(self):
        a = self.make()
        self.generate(a)
        a.refresh_from_db()
        path = Path(a.model_file.path)
        self.assertTrue(path.exists())
        self.client.delete(reverse("avatar-detail", args=[a.pk]))
        self.assertFalse(path.exists())

    def test_generation_is_rate_limited(self):
        a = self.make()
        codes = [self.generate(a).status_code for _ in range(12)]
        self.assertIn(429, codes)


# --avatar wizard rules from the finished design--
from .measurements import WIZARD, eu_to_length_cm, length_to_eu
from .services.generator import STAGE_KEYS, cancel_generation, run_generation, stage_states


class WizardRulesTests(BaseTest):
    def create(self, **over):
        return self.client.post(reverse("avatar-list"), self.payload(**over), format="json")

    def test_height_range_is_100_to_250(self):
        for ok, weight in ((100, 30), (250, 100), (172.5, 60)):
            Avatar.objects.all().delete()
            self.assertEqual(self.create(height_cm=ok, weight_kg=weight).status_code, 201, ok)
        for bad in (99, 99.9, 250.1, 251, 0, -5):
            self.assertEqual(self.create(height_cm=bad).status_code, 400, bad)

    def test_eu_foot_size_conversion_matches_the_design_example(self):
        self.assertEqual(eu_to_length_cm(42), 27.0)
        self.assertEqual(length_to_eu(27.0), 42)
        for eu in range(34, 51):
            self.assertEqual(length_to_eu(eu_to_length_cm(eu)), eu, eu)

    def test_foot_size_is_validated_and_the_length_is_derived(self):
        self.assertTrue(validate_measurements({"foot_size_eu": 33}))
        self.assertTrue(validate_measurements({"foot_size_eu": 51}))
        self.assertEqual(validate_measurements({"foot_size_eu": 42, "foot_length": 27.0}), {})
        r = self.create(measurements={**CORE, "foot_size_eu": 42})
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn("foot_length", r.data["estimated_fields"])
        self.assertNotIn("foot_size_eu", r.data["estimated_fields"])
        a = Avatar.objects.get(pk=r.data["id"])
        self.assertEqual(a.full_measurements()[0]["foot_length"], 27.0)

    def test_a_given_length_yields_an_estimated_eu_size_and_both_given_means_no_estimates(self):
        full, est = estimate_missing(180, "male", {"foot_length": 27.0})
        self.assertEqual((full["foot_size_eu"], "foot_size_eu" in est, "foot_length" in est), (42, True, False))
        full, est = estimate_missing(180, "male", {"foot_length": 27.0, "foot_size_eu": 43})
        self.assertEqual((full["foot_size_eu"], full["foot_length"]), (43, 27.0))
        self.assertTrue({"foot_length", "foot_size_eu"}.isdisjoint(est))

    def test_spec_endpoint_describes_the_wizard(self):
        rows = self.client.get(reverse("measurement-spec")).data
        self.assertEqual(len(rows), 25)
        main = [r for r in rows if not r["advanced"]]
        self.assertEqual([r["order"] for r in main], list(range(1, 15)))
        by_key = {r["key"]: r for r in rows}
        self.assertEqual((by_key["chest_circumference"]["order"], by_key["chest_circumference"]["step"]), (2, 2))
        self.assertEqual(by_key["foot_size_eu"]["unit"], "EU")
        self.assertEqual((by_key["foot_size_eu"]["step"], by_key["foot_size_eu"]["advanced"]), (3, False))
        self.assertEqual({r["step"] for r in rows if r["advanced"]}, {2, 3})
        self.assertEqual(sum(1 for r in rows if r["step"] == 2 and not r["advanced"]), 8)
        self.assertEqual(sum(1 for r in rows if r["step"] == 3 and not r["advanced"]), 6)
        self.assertEqual(sum(1 for r in rows if r["advanced"]), 11)
        for r in rows:
            self.assertEqual((len(r["steps"]["uk"]), len(r["steps"]["en"])), (3, 3), r["key"])
            self.assertTrue(all(r["steps"]["uk"]) and all(r["steps"]["en"]))
        self.assertEqual(set(WIZARD), set(SPEC))
        self.assertEqual(sorted(r["order"] for r in rows), list(range(1, 26)))


class AvatarLimitTests(BaseTest):
    def test_at_most_five_profiles_per_user(self):
        url = reverse("avatar-list")
        for i in range(5):
            self.assertEqual(self.client.post(url, self.payload(name=f"A{i}"), format="json").status_code, 201)
        r = self.client.post(url, self.payload(name="Sixth"), format="json")
        self.assertEqual((r.status_code, r.data["code"], r.data["limit"]), (400, "avatar_limit", 5))
        self.assertEqual(Avatar.objects.filter(user=self.user).count(), 5)
        victim = Avatar.objects.filter(user=self.user, is_default=False).first()
        self.client.delete(reverse("avatar-detail", args=[victim.pk]))
        self.assertEqual(self.client.post(url, self.payload(name="Again"), format="json").status_code, 201)

    def test_the_limit_is_per_user(self):
        for i in range(5):
            self.make(name=f"A{i}")
        self.client.force_authenticate(self.other)
        r = self.client.post(reverse("avatar-list"), self.payload(gender="male"), format="json")
        self.assertEqual(r.status_code, 201, r.data)


class StaleBannerTests(BaseTest):
    def set_age(self, avatar, days):
        Avatar.objects.filter(pk=avatar.pk).update(measurements_updated_at=timezone.now() - timezone.timedelta(days=days))

    def test_age_and_stale_flag_drive_the_update_measurements_banner(self):
        a = self.make()
        for days, stale in ((0, False), (29, False), (30, True), (31, True)):
            self.set_age(a, days)
            data = self.client.get(reverse("avatar-detail", args=[a.pk])).data
            self.assertEqual((data["measurements_age_days"], data["measurements_stale"]), (days, stale), days)

    def test_editing_measurements_resets_the_banner(self):
        a = self.make()
        self.set_age(a, 45)
        m = dict(a.measurements, waist_circumference=80)
        self.client.patch(reverse("avatar-detail", args=[a.pk]), {"measurements": m}, format="json")
        data = self.client.get(reverse("avatar-detail", args=[a.pk])).data
        self.assertEqual((data["measurements_age_days"], data["measurements_stale"]), (0, False))


@override_settings(MEDIA_ROOT=_TMP, FILE_ENCRYPTION_KEY=Fernet.generate_key().decode(), AVATAR_GENERATION_EAGER=True)
class FrontPhotoAndCancelTests(BaseTest):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP, ignore_errors=True)

    def photo(self, avatar, kind="front"):
        from django.core.files.base import ContentFile
        p = AvatarPhoto(avatar=avatar, kind=kind, quality={"ok": True})
        p.file.save(f"{p.pk}.jpg", ContentFile(make_photo().read()), save=False)
        p.save()

    def generate(self, a):
        return self.client.post(reverse("avatar-generate", args=[a.pk]))

    def cancel(self, a):
        return self.client.post(reverse("avatar-cancel", args=[a.pk]))

    def test_generation_needs_a_front_photo(self):
        a = self.make()
        r = self.generate(a)
        self.assertEqual((r.status_code, r.data["code"]), (400, "front_photo_required"))
        self.photo(a, "profile_left")
        self.photo(a, "profile_right")
        self.assertEqual(self.generate(a).data["code"], "front_photo_required")
        self.photo(a, "front")
        self.assertEqual(self.generate(a).status_code, 202)

    def test_cancel_without_a_model_returns_to_draft(self):
        a = self.make()
        self.photo(a)
        Avatar.objects.filter(pk=a.pk).update(status="processing", stage="face_mesh", progress=25,
                                              generation_run=uuid4(), processing_started_at=timezone.now())
        r = self.cancel(a)
        self.assertEqual((r.status_code, r.data["status"], r.data["progress"]), (200, "draft", 0))
        a.refresh_from_db()
        self.assertIsNone(a.generation_run)

    def test_cancelling_a_regeneration_keeps_the_previous_model(self):
        a = self.make()
        self.photo(a)
        self.generate(a)
        a.refresh_from_db()
        self.assertEqual(a.status, "ready")
        Avatar.objects.filter(pk=a.pk).update(status="processing", stage="body_mesh", progress=50,
                                              generation_run=uuid4(), processing_started_at=timezone.now())
        self.assertEqual(self.cancel(a).data["status"], "ready")
        self.assertEqual(self.client.get(reverse("avatar-model", args=[a.pk])).status_code, 200)

    def test_cancel_when_nothing_runs_and_foreign_avatars(self):
        a = self.make()
        self.assertEqual(self.cancel(a).status_code, 409)
        theirs = self.make(user=self.other, gender="male")
        Avatar.objects.filter(pk=theirs.pk).update(status="processing")
        self.assertEqual(self.cancel(theirs).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status, "processing")

    def test_a_cancelled_worker_cannot_overwrite_anything(self):
        a = self.make()
        self.photo(a)
        run_a, run_b = uuid4(), uuid4()
        Avatar.objects.filter(pk=a.pk).update(status="processing", generation_run=run_a, stage="body_analysis",
                                              processing_started_at=timezone.now())
        cancel_generation(Avatar.objects.get(pk=a.pk))
        run_generation(a.pk, run_a)
        a.refresh_from_db()
        self.assertEqual((a.status, a.model_file.name if a.model_file else None), ("draft", None))
        Avatar.objects.filter(pk=a.pk).update(status="processing", generation_run=run_b, stage="face_mesh", progress=25,
                                              processing_started_at=timezone.now())
        run_generation(a.pk, run_a)
        a.refresh_from_db()
        self.assertEqual((a.status, a.stage, a.progress, a.generation_run), ("processing", "face_mesh", 25, run_b))
        self.assertFalse(a.model_file)

    def test_status_endpoint_reports_rows_while_running(self):
        a = self.make()
        Avatar.objects.filter(pk=a.pk).update(status="processing", stage="body_mesh", progress=62,
                                              processing_started_at=timezone.now() - timezone.timedelta(seconds=7))
        st = self.client.get(reverse("avatar-generation-status", args=[a.pk])).data
        self.assertEqual([x["state"] for x in st["stages"]], ["done", "done", "current", "pending", "pending"])
        self.assertEqual(st["progress"], 62)
        self.assertGreaterEqual(st["elapsed_seconds"], 7)
        self.assertIsNone(st["generation_seconds"])

    def test_stage_states_for_every_status(self):
        keys = STAGE_KEYS
        self.assertEqual([x["state"] for x in stage_states("draft", "")], ["pending"] * 5)
        self.assertEqual([x["state"] for x in stage_states("ready", "done")], ["done"] * 5)
        self.assertEqual([x["state"] for x in stage_states("processing", "body_analysis")][:2], ["current", "pending"])
        self.assertEqual([x["state"] for x in stage_states("failed", "skin_texture")],
                         ["done", "done", "done", "failed", "pending"])
        self.assertEqual([x["key"] for x in stage_states("processing", "finalize")], keys)

    def test_a_restart_after_cancel_works(self):
        a = self.make()
        self.photo(a)
        Avatar.objects.filter(pk=a.pk).update(status="processing", generation_run=uuid4(),
                                              processing_started_at=timezone.now())
        self.assertEqual(self.generate(a).status_code, 409)
        self.cancel(a)
        self.assertEqual(self.generate(a).status_code, 202)
        self.assertEqual(Avatar.objects.get(pk=a.pk).status, "ready")