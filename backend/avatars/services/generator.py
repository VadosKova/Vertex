import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone
from django.utils.module_loading import import_string

from ..models import Avatar
from .glb import build_placeholder_glb

log = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

STAGES = [("body_analysis", 5), ("face_mesh", 25), ("body_mesh", 50), ("skin_texture", 75), ("finalize", 90)]
STAGE_KEYS = [k for k, _ in STAGES]

REFERENCE = {
    "male": {"chest": 0.55, "waist": 0.46, "hips": 0.55, "shoulders": 0.259},
    "female": {"chest": 0.52, "waist": 0.40, "hips": 0.57, "shoulders": 0.230},
}
MORPH_KEYS = {"chest": "chest_circumference", "waist": "waist_circumference", "hips": "hip_circumference", "shoulders": "shoulder_width"}
BODY_TYPE_BIAS = {"ectomorph": -0.05, "mesomorph": 0.0, "endomorph": 0.08}
STALE_AFTER = timezone.timedelta(minutes=5)


class _Abandoned(Exception):
    """The run was cancelled or superseded while it was working: stop silently, write nothing."""


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


def _running(avatar_id, run):
    return Avatar.objects.filter(pk=avatar_id, generation_run=run, status=Avatar.Status.PROCESSING)


def _enter(avatar_id, run, stage, progress):
    if not _running(avatar_id, run).update(stage=stage, progress=progress):
        raise _Abandoned()


def run_generation(avatar_id, run):
    stage = STAGE_KEYS[0]
    try:
        avatar = Avatar.objects.get(pk=avatar_id)

        stage = "body_analysis"
        _enter(avatar_id, run, stage, 5)
        params = compute_morph_params(avatar)
        full, _ = avatar.full_measurements()

        stage = "face_mesh"
        _enter(avatar_id, run, stage, 25)
        face_data = {}
        photo = avatar.photos.filter(kind="front").first()
        if photo:
            analyzer = import_string(getattr(settings, "AVATAR_FACE_ANALYZER", "avatars.services.face.BasicFaceAnalyzer"))()
            with photo.file.open("rb") as fh:
                face_data = analyzer.analyze(fh.read())

        stage = "body_mesh"
        _enter(avatar_id, run, stage, 50)
        glb = build_placeholder_glb(
            avatar.height_cm / 100, full["shoulder_width"] / 100 * 1.6, full["chest_circumference"] / 100 / 3.14 * 1.2,
            extras={"morph": params, "skin_rgb": face_data.get("skin_rgb")})

        stage = "skin_texture"
        _enter(avatar_id, run, stage, 75)

        stage = "finalize"
        _enter(avatar_id, run, stage, 90)
        if avatar.model_file:
            avatar.model_file.delete(save=False)
        avatar.model_file.save(f"{avatar.pk}.glb", ContentFile(glb), save=False)
        started = Avatar.objects.values_list("processing_started_at", flat=True).get(pk=avatar_id)
        seconds = round((timezone.now() - started).total_seconds(), 1) if started else None
        done = _running(avatar_id, run).update(
            model_file=avatar.model_file.name, morph_params=params, face_data=face_data,
            status=Avatar.Status.READY, stage="done", progress=100, needs_regeneration=False, error="",
            generation_seconds=seconds, generation_run=None)
        if not done:
            avatar.model_file.delete(save=False)
    except _Abandoned:
        return
    except Exception as exc:  # noqa: BLE001
        log.exception("Avatar generation failed")
        _running(avatar_id, run).update(status=Avatar.Status.FAILED, stage=stage, error=str(exc)[:200],
                                        generation_run=None)


def _run_in_worker(avatar_id, run):
    try:
        run_generation(avatar_id, run)
    finally:
        connection.close()


def is_busy(avatar: Avatar) -> bool:
    return (avatar.status == Avatar.Status.PROCESSING and avatar.processing_started_at is not None
            and timezone.now() - avatar.processing_started_at < STALE_AFTER)


def start_generation(avatar: Avatar):
    run = uuid.uuid4()
    Avatar.objects.filter(pk=avatar.pk).update(
        status=Avatar.Status.PROCESSING, stage=STAGE_KEYS[0], progress=5, error="", generation_seconds=None,
        processing_started_at=timezone.now(), generation_run=run)
    if getattr(settings, "AVATAR_GENERATION_EAGER", False):
        run_generation(avatar.pk, run)
    else:
        _executor.submit(_run_in_worker, avatar.pk, run)
    return run


def cancel_generation(avatar: Avatar):
    has_model = bool(avatar.model_file)
    Avatar.objects.filter(pk=avatar.pk, status=Avatar.Status.PROCESSING).update(
        status=Avatar.Status.READY if has_model else Avatar.Status.DRAFT, stage="",
        progress=100 if has_model else 0, generation_run=None, error="")


def stage_states(status, stage):
    if status == Avatar.Status.READY:
        return [{"key": k, "state": "done"} for k in STAGE_KEYS]
    if status not in (Avatar.Status.PROCESSING, Avatar.Status.FAILED) or stage not in STAGE_KEYS:
        return [{"key": k, "state": "pending"} for k in STAGE_KEYS]
    current = STAGE_KEYS.index(stage)
    mark = "current" if status == Avatar.Status.PROCESSING else "failed"
    return [{"key": k, "state": "done" if i < current else mark if i == current else "pending"}
            for i, k in enumerate(STAGE_KEYS)]
