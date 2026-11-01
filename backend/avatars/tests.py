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