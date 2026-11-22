import hashlib
import hmac
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

from .models import PasswordResetCode, User

CODE_TTL = 10 * 60
TOKEN_TTL = 10 * 60
RESEND_COOLDOWN = 45
MAX_CODES_PER_HOUR = 5
MAX_ATTEMPTS = 5
TOKEN_SALT = "vertex.password-reset"

TEXT = {
    "uk": ("Код відновлення пароля Vertex",
           "Ваш код відновлення: {code}\nВін діє {minutes} хв. Якщо ви не запитували відновлення пароля, "
           "просто проігноруйте цей лист."),
    "en": ("Vertex password reset code",
           "Your recovery code: {code}\nIt is valid for {minutes} minutes. If you did not request a password "
           "reset, just ignore this email."),
}


class Throttled(Exception):
    def __init__(self, wait):
        super().__init__(f"Retry in {wait}s")
        self.wait = max(1, int(wait))


class InvalidCode(Exception):
    pass


class InvalidToken(Exception):
    pass