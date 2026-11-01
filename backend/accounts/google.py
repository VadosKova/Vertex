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