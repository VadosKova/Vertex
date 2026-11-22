from datetime import timedelta
from unittest import mock

from django.core import mail, signing
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from . import reset
from .models import PasswordResetCode, User
from .passwords import validate_password_strength

OLD = "Old-passw0rd!"
NEW = "Brand-new-pass-9"


def code_from_mail(index=-1):
    return next(w for w in mail.outbox[index].body.split() if w.isdecimal() and len(w) == 6)


class ResetBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("vadym@example.com", OLD, username="Vadym", language="uk")

    def request(self, email="vadym@example.com"):
        return self.client.post(reverse("password-reset"), {"email": email}, format="json")

    def verify(self, code, email="vadym@example.com"):
        return self.client.post(reverse("password-reset-verify"), {"email": email, "code": code}, format="json")

    def confirm(self, token, password=NEW, **extra):
        return self.client.post(reverse("password-reset-confirm"),
                                {"reset_token": token, "new_password": password, **extra}, format="json")

    def full_flow_token(self):
        self.request()
        return self.verify(code_from_mail()).data["reset_token"]

    def age_codes(self, seconds):
        PasswordResetCode.objects.update(created_at=timezone.now() - timedelta(seconds=seconds))


class FullFlowTests(ResetBase):
    def test_forgot_otp_new_password(self):
        r = self.request()
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.data["email_masked"], r.data["resend_after"], r.data["expires_in"]), ("v***@example.com", 45, 600))
        self.assertEqual(len(mail.outbox), 1)
        code = code_from_mail()
        self.assertEqual(len(code), 6)
        v = self.verify(code)
        self.assertEqual(v.status_code, 200, v.data)
        self.assertEqual(self.confirm(v.data["reset_token"], new_password_confirm=NEW).status_code, 200)
        login = self.client.post(reverse("token"), {"email": "vadym@example.com", "password": NEW})
        self.assertEqual(login.status_code, 200)
        old = self.client.post(reverse("token"), {"email": "vadym@example.com", "password": OLD})
        self.assertEqual(old.status_code, 401)

    def test_only_a_hash_of_the_code_is_stored(self):
        self.request()
        code = code_from_mail()
        row = PasswordResetCode.objects.get()
        self.assertNotIn(code, row.code_hash)
        self.assertEqual(len(row.code_hash), 64)

    def test_email_text_follows_the_users_language_and_contains_the_ttl(self):
        self.request()
        self.assertIn("Код відновлення", mail.outbox[0].subject)
        self.assertIn("10 хв", mail.outbox[0].body)
        User.objects.filter(pk=self.user.pk).update(language="en")
        self.age_codes(100)
        self.request()
        self.assertIn("reset code", mail.outbox[1].subject)

    def test_email_matching_is_case_insensitive(self):
        self.assertEqual(self.request("VADYM@Example.com").status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.verify(code_from_mail(), email="Vadym@EXAMPLE.com").status_code, 200)

    def test_all_sessions_are_signed_out_after_the_reset(self):
        refresh = str(RefreshToken.for_user(self.user))
        token = self.full_flow_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": refresh}).status_code, 401)

    def test_google_only_accounts_can_set_a_password_this_way(self):
        g = User.objects.create_user("gina@example.com", None, username="Gina", google_sub="g-1")
        g.set_unusable_password()
        g.save()
        self.request("gina@example.com")
        token = self.verify(code_from_mail(), email="gina@example.com").data["reset_token"]
        self.assertEqual(self.confirm(token).status_code, 200)
        r = self.client.post(reverse("token"), {"email": "gina@example.com", "password": NEW})
        self.assertEqual(r.status_code, 200)


class PrivacyTests(ResetBase):
    def test_unknown_and_inactive_emails_get_the_same_answer_and_no_mail(self):
        User.objects.create_user("off@example.com", OLD, username="Off", is_active=False)
        known = self.request()
        for email in ("ghost@example.com", "off@example.com"):
            r = self.request(email)
            self.assertEqual(r.status_code, known.status_code)
            self.assertEqual(set(r.data), set(known.data))
            self.assertEqual((r.data["resend_after"], r.data["expires_in"]), (45, 600))
        self.assertEqual(len(mail.outbox), 1)

    def test_verify_fails_identically_for_unknown_and_wrong(self):
        self.request()
        wrong = self.verify("000000")
        ghost = self.verify("123456", email="ghost@example.com")
        self.assertEqual((wrong.status_code, wrong.data), (400, ghost.data and wrong.data))
        self.assertEqual(wrong.data, ghost.data)
        self.assertEqual(wrong.data["code"], "invalid_code")

    def test_cooldown_and_hourly_cap_also_apply_to_unknown_emails(self):
        self.assertEqual(self.request("ghost@example.com").status_code, 200)
        r = self.request("ghost@example.com")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.data["code"], "too_many_requests")


class ThrottleTests(ResetBase):
    def test_resend_cooldown_is_45_seconds(self):
        self.assertEqual(self.request().status_code, 200)
        r = self.request()
        self.assertEqual(r.status_code, 429)
        self.assertTrue(1 <= r.data["retry_after"] <= 45)
        self.assertEqual(r["Retry-After"], str(r.data["retry_after"]))
        self.assertEqual(len(mail.outbox), 1)
        self.age_codes(46)
        self.assertEqual(self.request().status_code, 200)
        self.assertEqual(len(mail.outbox), 2)

    def test_at_most_five_codes_per_hour(self):
        for _ in range(5):
            self.assertEqual(self.request().status_code, 200)
            self.age_codes(60)
        self.assertEqual(self.request().status_code, 429)
        self.age_codes(3700)
        self.assertEqual(self.request().status_code, 200)

    def test_a_new_code_cancels_the_previous_one(self):
        self.request()
        first = code_from_mail()
        self.age_codes(60)
        self.request()
        second = code_from_mail()
        self.assertNotEqual(first, second)
        self.assertEqual(self.verify(first).status_code, 400)
        self.assertEqual(self.verify(second).status_code, 200)


class CodeCheckTests(ResetBase):
    def test_five_wrong_guesses_burn_the_code(self):
        self.request()
        code = code_from_mail()
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(5):
            self.assertEqual(self.verify(wrong).status_code, 400)
        self.assertEqual(self.verify(code).status_code, 400)
        self.age_codes(60)
        self.request()
        self.assertEqual(self.verify(code_from_mail()).status_code, 200)

    def test_expired_code_and_bad_formats_are_rejected(self):
        self.request()
        code = code_from_mail()
        for bad in ("12345", "1234567", "abcdef", "12 456", "", "٠٠٠٠٠٠"):
            self.assertEqual(self.verify(bad).status_code, 400, bad)
        PasswordResetCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.verify(code).status_code, 400)

    def test_a_code_works_only_once(self):
        self.request()
        code = code_from_mail()
        self.assertEqual(self.verify(code).status_code, 200)
        self.assertEqual(self.verify(code).status_code, 400)

    def test_missing_fields(self):
        self.assertEqual(self.client.post(reverse("password-reset-verify"), {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(reverse("password-reset"), {"email": "nope"}, format="json").status_code, 400)


class ConfirmTests(ResetBase):
    def test_token_is_single_use(self):
        token = self.full_flow_token()
        self.assertEqual(self.confirm(token).status_code, 200)
        r = self.confirm(token, password="Another-pass-77")
        self.assertEqual((r.status_code, r.data["code"]), (400, "invalid_token"))

    def test_garbage_forged_and_expired_tokens(self):
        self.assertEqual(self.confirm("garbage").data["code"], "invalid_token")
        forged = signing.dumps({"u": self.user.pk, "c": 1}, salt="some.other.salt")
        self.assertEqual(self.confirm(forged).data["code"], "invalid_token")
        token = self.full_flow_token()
        with mock.patch("accounts.reset.TOKEN_TTL", -1):
            self.assertEqual(self.confirm(token).data["code"], "invalid_token")

    def test_a_code_that_was_never_verified_cannot_reset_anything(self):
        self.request()
        row = PasswordResetCode.objects.get()
        token = signing.dumps({"u": self.user.pk, "c": row.pk}, salt=reset.TOKEN_SALT)
        self.assertEqual(self.confirm(token).data["code"], "invalid_token")
        self.assertTrue(self.user.check_password(OLD))

    def test_password_rules_from_the_new_password_screen(self):
        cases = {"Sh0rt!": "at least 8", "NoDigits-here": "digit", "NoSpecial123x": "special",
                 "Password1!": "", "1234567890": "special"}
        for password, fragment in cases.items():
            token = self.full_flow_token()
            r = self.confirm(token, password=password)
            self.assertEqual(r.status_code, 400, password)
            self.assertTrue(any(fragment in m.lower() for m in map(str, r.data["new_password"])), (password, r.data))
            self.age_codes(60)
        self.assertTrue(self.user.check_password(OLD))

    def test_a_failed_attempt_keeps_the_token_usable(self):
        token = self.full_flow_token()
        self.assertEqual(self.confirm(token, password="weak").status_code, 400)
        self.assertEqual(self.confirm(token).status_code, 200)

    def test_new_password_must_differ_from_the_current_one(self):
        token = self.full_flow_token()
        r = self.confirm(token, password=OLD)
        self.assertEqual(r.status_code, 400)
        self.assertIn("differ", str(r.data["new_password"]))

    def test_confirmation_field_must_match_when_sent(self):
        token = self.full_flow_token()
        r = self.confirm(token, new_password_confirm="Different-pass-1")
        self.assertEqual(r.status_code, 400)
        self.assertIn("new_password_confirm", r.data)

    def test_the_password_policy_also_applies_at_registration(self):
        base = {"email": "n@example.com", "username": "Nick", "gender": "male"}
        self.assertEqual(self.client.post(reverse("register"), {**base, "password": "NoSpecial123x"}).status_code, 400)
        self.assertEqual(self.client.post(reverse("register"), {**base, "password": "No-digits-here"}).status_code, 400)
        self.assertEqual(self.client.post(reverse("register"), {**base, "password": "Good-pass-1"}).status_code, 201)


class PolicyUnitTests(APITestCase):
    def test_validator(self):
        self.assertEqual(validate_password_strength("Good-pass-1"), "Good-pass-1")
        self.assertEqual(validate_password_strength("Парол_1234"), "Парол_1234")
        for bad in ("short1!", "nodigit-pass", "nospecial12345", "x" * 129 + "1!"):
            with self.assertRaises(Exception):
                validate_password_strength(bad)

    def test_mask_email(self):
        self.assertEqual(reset.mask_email("vadym@example.com"), "v***@example.com")
        self.assertEqual(reset.mask_email("a@x.io"), "a***@x.io")


class LogoutTests(ResetBase):
    def login(self):
        r = self.client.post(reverse("token"), {"email": "vadym@example.com", "password": OLD})
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return r.data["refresh"]

    def test_logout_revokes_the_refresh_token_and_is_idempotent(self):
        refresh = self.login()
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": refresh}, format="json").status_code, 204)
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": refresh}).status_code, 401)
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": refresh}, format="json").status_code, 204)
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": "garbage"}, format="json").status_code, 204)

    def test_logout_does_not_touch_other_peoples_tokens(self):
        other = User.objects.create_user("bob@example.com", OLD, username="Bob")
        theirs = str(RefreshToken.for_user(other))
        self.login()
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": theirs}, format="json").status_code, 204)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": theirs}).status_code, 200)

    def test_logout_requires_login_and_a_body(self):
        self.assertEqual(self.client.post(reverse("logout"), {"refresh": "x"}, format="json").status_code, 401)
        self.login()
        self.assertEqual(self.client.post(reverse("logout"), {}, format="json").status_code, 400)
