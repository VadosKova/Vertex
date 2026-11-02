from django.conf import settings
from django.db import models


ZONES = {
    "chest": "chest_circumference",
    "waist": "waist_circumference",
    "hips": "hip_circumference",
    "shoulders": "shoulder_width",
    "inseam": "inseam",
}