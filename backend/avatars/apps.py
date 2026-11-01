from django.apps import AppConfig


class AvatarsConfig(AppConfig):
    name = "avatars"

    def ready(self):
        from . import signals