from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import AvatarPhoto


@receiver(post_delete, sender=AvatarPhoto)
def delete_photo_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)