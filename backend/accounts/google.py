from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

User = get_user_model()


class GoogleNotConfigured(Exception):
    pass


class InvalidGoogleToken(Exception):
    pass


def verify_google_token(token: str) -> dict:
    client_ids = getattr(settings, "GOOGLE_OAUTH_CLIENT_IDS", [])
    if not client_ids:
        raise GoogleNotConfigured()
    try:
        return id_token.verify_oauth2_token(token, google_requests.Request(), audience=client_ids)
    except ValueError as exc:
        raise InvalidGoogleToken() from exc


def default_username(raw, email):
    name = " ".join((raw or "").split())[:30].strip()
    if len(name) < 2:
        name = email.split("@")[0][:30]
    return name if len(name) >= 2 else "User"


@transaction.atomic
def sign_in_with_google(info: dict, username=None, gender=None):
    sub, email = info["sub"], info["email"].strip().lower()

    user = User.objects.filter(google_sub=sub).first()
    if user:
        return user, False

    user = User.objects.filter(email__iexact=email).first()
    if user:
        user.google_sub = sub
        user.set_unusable_password()
        user.save(update_fields=["google_sub", "password"])
        return user, False

    user = User(email=email, google_sub=sub, gender=gender or "",
                username=username or default_username(info.get("name"), email))
    user.set_unusable_password()
    user.save()
    return user, True