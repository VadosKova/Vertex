import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import close_old_connections
from django.utils import timezone
from django.utils.module_loading import import_string

from ..models import Avatar
from .glb import build_placeholder_glb

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)


REFERENCE = {
    "male": {"chest": 0.55, "waist": 0.46, "hips": 0.55, "shoulders": 0.259},
    "female": {"chest": 0.52, "waist": 0.40, "hips": 0.57, "shoulders": 0.230},
}
MORPH_KEYS = {"chest": "chest_circumference", "waist": "waist_circumference",
              "hips": "hip_circumference", "shoulders": "shoulder_width"}
BODY_TYPE_BIAS = {"ectomorph": -0.05, "mesomorph": 0.0, "endomorph": 0.08}


def compute_morph_params(avatar: Avatar) -> dict:
    full, estimated = avatar.full_measurements()
    ref = REFERENCE[avatar.gender]
    params = {}
    for shape, key in MORPH_KEYS.items():
        expected = ref[shape] * avatar.height_cm
        params[shape] = round(max(-0.5, min(0.5, (full[key] - expected) / expected)), 3)
    bmi = avatar.weight_kg / (avatar.height_cm / 100) ** 2
    params["bmi"] = round(bmi, 1)
    params["body_type_bias"] = BODY_TYPE_BIAS[avatar.body_type]
    params["height_m"] = round(avatar.height_cm / 100, 3)
    params["estimated_fields"] = estimated
    return params


def _progress(avatar, stage, pct):
    Avatar.objects.filter(pk=avatar.pk).update(stage=stage, progress=pct)