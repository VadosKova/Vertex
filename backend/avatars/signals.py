from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Avatar, AvatarPhoto


@receiver(post_delete, sender=AvatarPhoto)
def delete_photo_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)


@receiver(post_delete, sender=Avatar)
def delete_model_file(sender, instance, **kwargs):
    if instance.model_file:
        instance.model_file.delete(save=False)