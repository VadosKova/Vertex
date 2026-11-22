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


def normalize(email):
    return email.strip().lower()


def mask_email(email):
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def _hash(user_id, code):
    return hmac.new(settings.SECRET_KEY.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _throttle_unknown(email):
    now = time.time()
    last = cache.get(f"pwr:last:{email}")
    if last is not None and now - last < RESEND_COOLDOWN:
        raise Throttled(RESEND_COOLDOWN - (now - last))
    count = cache.get(f"pwr:hour:{email}", 0)
    if count >= MAX_CODES_PER_HOUR:
        raise Throttled(600)
    cache.set(f"pwr:last:{email}", now, RESEND_COOLDOWN)
    cache.set(f"pwr:hour:{email}", count + 1, 3600)


def _throttle_known(user):
    now = timezone.now()
    last = user.reset_codes.order_by("-created_at").first()
    if last and (now - last.created_at).total_seconds() < RESEND_COOLDOWN:
        raise Throttled(RESEND_COOLDOWN - (now - last.created_at).total_seconds())
    if user.reset_codes.filter(created_at__gte=now - timedelta(hours=1)).count() >= MAX_CODES_PER_HOUR:
        raise Throttled(600)


def request_code(email):
    email = normalize(email)
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is None:
        _throttle_unknown(email)
    else:
        _throttle_known(user)
        code = f"{secrets.randbelow(10 ** 6):06d}"
        user.reset_codes.filter(used_at__isnull=True).update(used_at=timezone.now())
        PasswordResetCode.objects.create(user=user, code_hash=_hash(user.pk, code),
                                         expires_at=timezone.now() + timedelta(seconds=CODE_TTL))
        subject, body = TEXT.get(user.language, TEXT["uk"])
        send_mail(subject, body.format(code=code, minutes=CODE_TTL // 60), settings.DEFAULT_FROM_EMAIL, [user.email])
    return {"email_masked": mask_email(email), "resend_after": RESEND_COOLDOWN, "expires_in": CODE_TTL}