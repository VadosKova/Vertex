from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        MEASUREMENT_REMINDER = "measurement_reminder"
        AVATAR_READY = "avatar_ready"
        PRICE_DROP = "price_drop"
        NEW_COLLECTION = "new_collection"

    class Action(models.TextChoices):
        UPDATE_MEASUREMENTS = "update_measurements"
        OPEN_AVATAR = "open_avatar"
        OPEN_PRODUCT = "open_product"
        OPEN_CATALOG = "open_catalog"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=300)
    action = models.CharField(max_length=30, choices=Action.choices, blank=True)
    data = models.JSONField(default=dict, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class DeviceToken(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="device_tokens")
    token = models.CharField(max_length=4096, unique=True)
    platform = models.CharField(max_length=10, default="android", choices=[("android", "Android"), ("ios", "iOS")])
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)