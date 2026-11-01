import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .measurements import estimate_missing


class Avatar(models.Model):
    class Gender(models.TextChoices):
        MALE = "male"
        FEMALE = "female"

    class BodyType(models.TextChoices):
        ECTOMORPH = "ectomorph"
        MESOMORPH = "mesomorph"
        ENDOMORPH = "endomorph"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avatars")
    name = models.CharField(max_length=60)
    gender = models.CharField(max_length=6, choices=Gender.choices)
    age = models.PositiveSmallIntegerField()
    height_cm = models.FloatField()
    weight_kg = models.FloatField()
    body_type = models.CharField(max_length=10, choices=BodyType.choices, default=BodyType.MESOMORPH)
    measurements = models.JSONField(default=dict, blank=True)
    measurements_updated_at = models.DateTimeField(default=timezone.now)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(is_default=True), name="one_default_avatar_per_user"),
        ]

    def __str__(self):
        return f"{self.name} ({self.user})"

    def full_measurements(self):
        return estimate_missing(self.height_cm, self.gender, self.measurements)


class AvatarDraft(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="avatar_draft")
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)