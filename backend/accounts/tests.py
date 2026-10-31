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
        self.assertEqual(again.status_code, 400)  # token is single-use

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
