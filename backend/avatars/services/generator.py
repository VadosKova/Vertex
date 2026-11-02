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


def run_generation(avatar_id):
    close_old_connections()
    try:
        avatar = Avatar.objects.get(pk=avatar_id)
        _progress(avatar, "face_analysis", 25)
        face_data = {}
        photo = avatar.photos.first()
        if photo:
            analyzer = import_string(getattr(settings, "AVATAR_FACE_ANALYZER", "avatars.services.face.BasicFaceAnalyzer"))()
            with photo.file.open("rb") as fh:
                face_data = analyzer.analyze(fh.read())
        _progress(avatar, "morphing", 55)
        params = compute_morph_params(avatar)
        full, _ = avatar.full_measurements()
        _progress(avatar, "exporting", 85)
        glb = build_placeholder_glb(
            avatar.height_cm / 100,
            full["shoulder_width"] / 100 * 1.6,
            full["chest_circumference"] / 100 / 3.14 * 1.2,
            extras={"morph": params, "skin_rgb": face_data.get("skin_rgb")},
        )
        if avatar.model_file:
            avatar.model_file.delete(save=False)
        avatar.model_file.save(f"{avatar.pk}.glb", ContentFile(glb), save=False)
        Avatar.objects.filter(pk=avatar.pk).update(
            model_file=avatar.model_file.name, morph_params=params, face_data=face_data,
            status=Avatar.Status.READY, stage="done", progress=100, needs_regeneration=False, error="")
    except Exception as exc:  # noqa: BLE001
        log.exception("Avatar generation failed")
        Avatar.objects.filter(pk=avatar_id).update(status=Avatar.Status.FAILED, stage="failed", error=str(exc)[:200])
    finally:
        close_old_connections()


STALE_AFTER = timezone.timedelta(minutes=5)


def is_busy(avatar: Avatar) -> bool:
    return (avatar.status == Avatar.Status.PROCESSING and avatar.processing_started_at is not None
            and timezone.now() - avatar.processing_started_at < STALE_AFTER)


def start_generation(avatar: Avatar):
    Avatar.objects.filter(pk=avatar.pk).update(
        status=Avatar.Status.PROCESSING, stage="validating", progress=5, error="",
        processing_started_at=timezone.now())
    if getattr(settings, "AVATAR_GENERATION_EAGER", False):
        run_generation(avatar.pk)
    else:
        _executor.submit(run_generation, avatar.pk)