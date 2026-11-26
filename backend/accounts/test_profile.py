from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User

PASSWORD = "S3cure-pass-word"


class ProfileBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice", gender="female")
        self.client.force_authenticate(self.user)

    def patch(self, **data):
        return self.client.patch(reverse("me"), data, format="json")


class SettingsTests(ProfileBase):
    def test_defaults_match_the_design(self):
        d = self.client.get(reverse("me")).data
        self.assertEqual((d["reminder_enabled"], d["reminder_day"], d["reminder_time"], d["timezone"]),
                         (True, 1, "10:00", "Europe/Kyiv"))
        self.assertEqual((d["push_enabled"], d["in_app_enabled"]), (True, True))

    def test_every_switch_and_value_can_be_changed(self):
        r = self.patch(reminder_enabled=False, reminder_day=15, reminder_time="18:30", timezone="America/New_York",
                       push_enabled=False, in_app_enabled=False)
        self.assertEqual(r.status_code, 200, r.data)
        self.user.refresh_from_db()
        self.assertEqual((self.user.reminder_enabled, self.user.reminder_day, self.user.timezone_name,
                          self.user.push_enabled, self.user.in_app_enabled),
                         (False, 15, "America/New_York", False, False))
        self.assertEqual((self.user.reminder_time.hour, self.user.reminder_time.minute), (18, 30))
        d = self.client.get(reverse("me")).data
        self.assertEqual((d["reminder_time"], d["reminder_day"], d["timezone"]), ("18:30", 15, "America/New_York"))

    def test_the_day_is_limited_to_1_28_so_every_month_has_it(self):
        for ok in (1, 28):
            self.assertEqual(self.patch(reminder_day=ok).status_code, 200, ok)
        for bad in (0, 29, 31, -1, "x"):
            self.assertEqual(self.patch(reminder_day=bad).status_code, 400, bad)

    def test_time_formats(self):
        self.assertEqual(self.patch(reminder_time="07:05").data["reminder_time"], "07:05")
        self.assertEqual(self.patch(reminder_time="07:05:00").data["reminder_time"], "07:05")
        for bad in ("25:00", "10:60", "ten", "", "7"):
            self.assertEqual(self.patch(reminder_time=bad).status_code, 400, bad)

    def test_time_zone_must_be_a_real_iana_name(self):
        self.assertEqual(self.patch(timezone="Asia/Tokyo").status_code, 200)
        for bad in ("Mars/Phobos", "../../etc/passwd", "", "Kyiv", "x" * 100):
            self.assertEqual(self.patch(timezone=bad).status_code, 400, bad)
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone_name, "Asia/Tokyo")

    def test_settings_are_returned_after_registration_and_login_too(self):
        self.client.force_authenticate(None)
        r = self.client.post(reverse("register"), {"email": "n@example.com", "password": "Good-pass-1",
                                                   "username": "Nick", "gender": "male"})
        self.assertEqual((r.data["user"]["reminder_day"], r.data["user"]["push_enabled"]), (1, True))
        r = self.client.post(reverse("token"), {"email": "n@example.com", "password": "Good-pass-1"})
        self.assertEqual(r.data["user"]["reminder_time"], "10:00")

    def test_other_users_are_not_affected(self):
        bob = User.objects.create_user("bob@example.com", PASSWORD, username="Bob")
        self.patch(reminder_day=20, push_enabled=False)
        bob.refresh_from_db()
        self.assertEqual((bob.reminder_day, bob.push_enabled), (1, True))


class RememberMeTests(ProfileBase):
    def login(self, **extra):
        self.client.force_authenticate(None)
        return self.client.post(reverse("token"), {"email": "alice@example.com", "password": PASSWORD, **extra},
                                format="json")

    def lifetime_days(self, refresh):
        token = RefreshToken(refresh)
        return round((token["exp"] - token["iat"]) / 86400)

    def test_default_and_ticked_box_last_30_days_unticked_one_day(self):
        self.assertEqual(self.lifetime_days(self.login().data["refresh"]), 30)
        self.assertEqual(self.lifetime_days(self.login(remember_me=True).data["refresh"]), 30)
        self.assertEqual(self.lifetime_days(self.login(remember_me=False).data["refresh"]), 1)

    def test_the_response_shape_and_the_tokens_work(self):
        r = self.login(remember_me=False)
        self.assertEqual(r.status_code, 200)
        self.assertEqual({"access", "refresh", "user"}, set(r.data))
        refreshed = self.client.post(reverse("token-refresh"), {"refresh": r.data["refresh"]})
        self.assertEqual(refreshed.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.assertEqual(self.client.get(reverse("me")).status_code, 200)

    def test_a_short_session_can_be_revoked_like_any_other(self):
        r = self.login(remember_me=False)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        self.client.post(reverse("logout"), {"refresh": r.data["refresh"]}, format="json")
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("token-refresh"), {"refresh": r.data["refresh"]}).status_code, 401)

    def test_bad_input_and_credentials(self):
        self.assertEqual(self.login(remember_me="maybe").status_code, 400)
        self.client.force_authenticate(None)
        r = self.client.post(reverse("token"), {"email": "alice@example.com", "password": "nope", "remember_me": False})
        self.assertEqual(r.status_code, 401)

    def test_mixed_case_email_still_works(self):
        self.client.force_authenticate(None)
        r = self.client.post(reverse("token"), {"email": " ALICE@Example.com ", "password": PASSWORD})
        self.assertEqual(r.status_code, 200)

    def test_the_lifetimes_can_be_configured(self):
        from django.test import override_settings
        with override_settings(REFRESH_REMEMBER_DAYS=60, REFRESH_SESSION_DAYS=2):
            self.assertEqual(self.lifetime_days(self.login().data["refresh"]), 60)
            self.assertEqual(self.lifetime_days(self.login(remember_me=False).data["refresh"]), 2)