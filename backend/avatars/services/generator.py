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