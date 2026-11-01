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
        self.user.refresh_from_db()  # the logged-in object must see the change
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