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