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
    def test_spec_covers_all_24_fields_from_tz(self):
        self.assertEqual(len(SPEC), 24)
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

    def test_at_most_three_photos(self):
        a = self.make()
        for _ in range(settings.MAX_PHOTOS_PER_AVATAR):
            self.assertEqual(self.upload(a).status_code, 201)
        self.assertEqual(self.upload(a).status_code, 400)

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