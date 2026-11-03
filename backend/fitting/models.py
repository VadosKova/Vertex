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