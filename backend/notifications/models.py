from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        MEASUREMENT_REMINDER = "measurement_reminder"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=300)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]