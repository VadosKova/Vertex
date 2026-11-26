import logging

from django.conf import settings
from django.utils.module_loading import import_string

log = logging.getLogger(__name__)


class NullPushBackend:
    def send(self, tokens, title, body, data):
        return []


class ConsolePushBackend:
    def send(self, tokens, title, body, data):
        for token in tokens:
            log.info("PUSH to %s…: %s | %s | %s", token[:12], title, body, data)
        return []


def get_backend():
    return import_string(getattr(settings, "PUSH_BACKEND", "notifications.push.NullPushBackend"))()