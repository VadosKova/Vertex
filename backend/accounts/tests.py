from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import User

PASSWORD = "S3cure-pass-word"
REG = {"username": "Vadym", "gender": "male"}


class AuthTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice")

    def test_register_returns_tokens_and_lowercases_email(self):
        r = self.client.post(reverse("register"), {"email": "New@Example.com", "password": "Another-pass-1", **REG})
        self.assertEqual(r.status_code, 201)
        self.assertIn("access", r.data)
        self.assertEqual(r.data["user"]["email"], "new@example.com")
        self.assertEqual(r.data["user"]["language"], "uk")
        self.assertEqual((r.data["user"]["username"], r.data["user"]["gender"]), ("Vadym", "male"))

    def test_register_requires_username_and_gender(self):
        base = {"email": "n@example.com", "password": "Another-pass-1"}
        r = self.client.post(reverse("register"), base)
        self.assertEqual(r.status_code, 400)
        self.assertIn("username", r.data)
        self.assertIn("gender", r.data)
        self.assertEqual(self.client.post(reverse("register"), {**base, "username": "Vadym"}).status_code, 400)
        self.assertEqual(self.client.post(reverse("register"), {**base, "gender": "male"}).status_code, 400)

    def test_register_validates_username_and_gender(self):
        base = {"email": "n@example.com", "password": "Another-pass-1"}
        for bad in ({"username": "   ", "gender": "male"}, {"username": "V", "gender": "male"},
                    {"username": "x" * 31, "gender": "male"}, {"username": "Vadym", "gender": "other"}):
            self.assertEqual(self.client.post(reverse("register"), {**base, **bad}).status_code, 400, bad)

    def test_register_normalises_username_whitespace(self):
        r = self.client.post(reverse("register"), {"email": "n@example.com", "password": "Another-pass-1",
                                                   "username": "  Vadym   K  ", "gender": "female"})
        self.assertEqual(r.data["user"]["username"], "Vadym K")

    def test_same_username_allowed_for_different_users(self):
        r = self.client.post(reverse("register"), {"email": "n@example.com", "password": "Another-pass-1",
                                                   "username": "Alice", "gender": "female"})
        self.assertEqual(r.status_code, 201)

    def test_register_rejects_duplicate_and_weak_password(self):
        r = self.client.post(reverse("register"), {"email": "ALICE@example.com", "password": "Another-pass-1", **REG})
        self.assertEqual(r.status_code, 400)
        r = self.client.post(reverse("register"), {"email": "x@example.com", "password": "12345678", **REG})
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)

    def test_login_mixed_case_email_and_refresh(self):
        r = self.client.post(reverse("token"), {"email": "ALICE@example.com", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)
        r2 = self.client.post(reverse("token-refresh"), {"refresh": r.data["refresh"]})
        self.assertEqual(r2.status_code, 200)
        self.assertIn("access", r2.data)

    def test_login_wrong_password(self):
        r = self.client.post(reverse("token"), {"email": "alice@example.com", "password": "nope"})
        self.assertEqual(r.status_code, 401)

    def test_me_requires_jwt(self):
        self.assertEqual(self.client.get(reverse("me")).status_code, 401)

    def test_password_reset_flow(self):
        r = self.client.post(reverse("password-reset"), {"email": "alice@example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        uid = body.split("uid=")[1].split("&")[0]
        token = body.split("token=")[1].split()[0]
        bad = self.client.post(reverse("password-reset-confirm"),
                               {"uid": uid, "token": "bad", "new_password": "Brand-new-pass-9"})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(reverse("password-reset-confirm"),
                              {"uid": uid, "token": token, "new_password": "Brand-new-pass-9"})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(User.objects.get(email="alice@example.com").check_password("Brand-new-pass-9"))
        again = self.client.post(reverse("password-reset-confirm"),
                                 {"uid": uid, "token": token, "new_password": "Third-pass-word-3"})
        self.assertEqual(again.status_code, 400)

    def test_password_reset_does_not_reveal_unknown_email(self):
        r = self.client.post(reverse("password-reset"), {"email": "ghost@example.com"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_password_reset_email_uses_user_language(self):
        User.objects.filter(email="alice@example.com").update(language="en")
        self.client.post(reverse("password-reset"), {"email": "alice@example.com"})
        self.assertIn("password reset", mail.outbox[0].subject)


class SettingsTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice")
        self.client.force_authenticate(self.user)

    def test_update_language_theme_reminder(self):
        r = self.client.patch(reverse("me"), {"language": "en", "theme": "dark", "reminder_enabled": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.language, self.user.theme, self.user.reminder_enabled), ("en", "dark", False))

    def test_change_username_and_gender(self):
        r = self.client.patch(reverse("me"), {"username": "  Новий Нік ", "gender": "female"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data["username"], r.data["gender"]), ("Новий Нік", "female"))
        self.assertEqual(self.client.patch(reverse("me"), {"username": "A"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(reverse("me"), {"username": ""}, format="json").status_code, 400)
        self.assertEqual(self.client.get(reverse("me")).data["username"], "Новий Нік")

    def test_invalid_language_rejected_and_email_readonly(self):
        self.assertEqual(self.client.patch(reverse("me"), {"language": "fr"}, format="json").status_code, 400)
        self.client.patch(reverse("me"), {"email": "evil@example.com"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "alice@example.com")

    def test_delete_account(self):
        self.assertEqual(self.client.delete(reverse("me")).status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())


# --Google sign-in--
from unittest import mock

from django.test import override_settings

from .google import InvalidGoogleToken

GOOGLE = {"sub": "google-123", "email": "gina@example.com", "email_verified": True, "name": "Gina Green"}


def google_login(client, claims=None, **extra):
    claims = {**GOOGLE, **(claims or {})}
    with mock.patch("accounts.views.verify_google_token", return_value=claims):
        return client.post(reverse("google-login"), {"id_token": "fake", **extra}, format="json")


class GoogleLoginTests(APITestCase):
    def setUp(self):
        cache.clear()

    def test_new_google_user_is_created_with_tokens(self):
        r = google_login(self.client)
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["created"])
        self.assertIn("access", r.data)
        self.assertEqual((r.data["user"]["email"], r.data["user"]["username"]), ("gina@example.com", "Gina Green"))
        self.assertFalse(r.data["profile_complete"])
        user = User.objects.get(email="gina@example.com")
        self.assertEqual(user.google_sub, "google-123")
        self.assertFalse(user.has_usable_password())

    def test_username_and_gender_from_register_screen_are_used_for_new_accounts(self):
        r = google_login(self.client, username="Гіна", gender="female")
        self.assertEqual((r.data["user"]["username"], r.data["user"]["gender"]), ("Гіна", "female"))
        self.assertTrue(r.data["profile_complete"])

    def test_second_login_returns_same_user(self):
        google_login(self.client)
        r = google_login(self.client, username="Ignored", gender="male")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["created"])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(r.data["user"]["username"], "Gina Green")

    def test_google_id_wins_over_changed_email(self):
        google_login(self.client)
        r = google_login(self.client, {"email": "new-address@example.com"})
        self.assertEqual((r.status_code, User.objects.count()), (200, 1))

    def test_links_existing_password_account_and_invalidates_password(self):
        User.objects.create_user("gina@example.com", PASSWORD, username="Gina")
        r = google_login(self.client, {"email": "Gina@Example.com"})
        self.assertEqual((r.status_code, r.data["created"]), (200, False))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().google_sub, "google-123")
        bad = self.client.post(reverse("token"), {"email": "gina@example.com", "password": PASSWORD})
        self.assertEqual(bad.status_code, 401)

    def test_google_account_can_set_a_password_via_reset(self):
        google_login(self.client)
        self.client.post(reverse("password-reset"), {"email": "gina@example.com"})
        body = mail.outbox[0].body
        uid, token = body.split("uid=")[1].split("&")[0], body.split("token=")[1].split()[0]
        ok = self.client.post(reverse("password-reset-confirm"),
                              {"uid": uid, "token": token, "new_password": "Brand-new-pass-9"})
        self.assertEqual(ok.status_code, 200)
        r = self.client.post(reverse("token"), {"email": "gina@example.com", "password": "Brand-new-pass-9"})
        self.assertEqual(r.status_code, 200)

    def test_unverified_email_is_rejected(self):
        r = google_login(self.client, {"email_verified": False})
        self.assertEqual(r.status_code, 401)
        self.assertFalse(User.objects.exists())

    def test_invalid_token_gives_401(self):
        with mock.patch("accounts.views.verify_google_token", side_effect=InvalidGoogleToken):
            r = self.client.post(reverse("google-login"), {"id_token": "garbage"}, format="json")
        self.assertEqual(r.status_code, 401)

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=[])
    def test_not_configured_gives_503(self):
        r = self.client.post(reverse("google-login"), {"id_token": "x"}, format="json")
        self.assertEqual(r.status_code, 503)

    @override_settings(GOOGLE_OAUTH_CLIENT_IDS=["web-id", "android-id"])
    def test_verifier_passes_our_client_ids_as_audience_and_maps_errors(self):
        with mock.patch("accounts.google.id_token.verify_oauth2_token", return_value=GOOGLE) as v:
            r = self.client.post(reverse("google-login"), {"id_token": "tok"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(v.call_args.kwargs["audience"], ["web-id", "android-id"])
        with mock.patch("accounts.google.id_token.verify_oauth2_token", side_effect=ValueError("wrong audience")):
            r = self.client.post(reverse("google-login"), {"id_token": "tok"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_disabled_account_cannot_sign_in(self):
        User.objects.create_user("gina@example.com", PASSWORD, username="Gina", is_active=False)
        self.assertEqual(google_login(self.client).status_code, 403)

    def test_input_validation(self):
        self.assertEqual(self.client.post(reverse("google-login"), {}, format="json").status_code, 400)
        self.assertEqual(google_login(self.client, gender="other").status_code, 400)
        self.assertEqual(google_login(self.client, username="G").status_code, 400)

    def test_default_username_fallbacks(self):
        r = google_login(self.client, {"name": "X" * 50})
        self.assertEqual(len(r.data["user"]["username"]), 30)
        r = google_login(self.client, {"sub": "s2", "email": "ab.cd@example.com", "name": ""})
        self.assertEqual(r.data["user"]["username"], "ab.cd")
        r = google_login(self.client, {"sub": "s3", "email": "q@example.com", "name": "Q"})
        self.assertEqual(r.data["user"]["username"], "User")