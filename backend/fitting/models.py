import uuid

from django.conf import settings
from django.db import models

from avatars.models import Avatar
from catalog.models import Product


class TryOnSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tryon_sessions")
    avatar = models.ForeignKey(Avatar, on_delete=models.CASCADE, related_name="tryon_sessions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class TryOnItem(models.Model):
    session = models.ForeignKey(TryOnSession, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    size_label = models.CharField(max_length=10)
    visible = models.BooleanField(default=True)
    layer = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["layer", "id"]
        constraints = [models.UniqueConstraint(fields=["session", "product"], name="one_layer_per_product")]