import shutil
import tempfile
from datetime import datetime, time, timedelta, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from avatars.models import Avatar
from catalog.models import Brand, Category, Product, ProductSize
from fitting.models import TryOnItem, TryOnSession

from .models import DeviceToken, Notification
from .services import (notify, notify_avatar_ready, notify_price_drops, reminder_due, send_due_reminders,
                       send_new_collection_digests, users_due_for_reminder)

PASSWORD = "S3cure-pass-word"
BODY = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=dt_timezone.utc)
Kind = Notification.Kind


class RecordingPush:
    calls = []
    invalid = []

    def send(self, tokens, title, body, data):
        RecordingPush.calls.append({"tokens": list(tokens), "title": title, "body": body, "data": data})
        return [t for t in tokens if t in RecordingPush.invalid]


class ExplodingPush:
    def send(self, tokens, title, body, data):
        raise RuntimeError("FCM is down")


@override_settings(PUSH_BACKEND="notifications.tests.RecordingPush")
class Base(APITestCase):
    def setUp(self):
        cache.clear()
        RecordingPush.calls, RecordingPush.invalid = [], []
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice", gender="male")
        self.other = User.objects.create_user("bob@example.com", PASSWORD, username="Bob", gender="male")
        self.client.force_authenticate(self.user)

    def make_avatar(self, user=None, days_old=30, **over):
        a = Avatar.objects.create(user=user or self.user, name="Main", gender="male", age=25, height_cm=180,
                                  weight_kg=75, measurements=dict(BODY), is_default=over.pop("is_default", True), **over)
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=NOW - timedelta(days=days_old))
        return a

    def device(self, user=None, token="fcm-token-aaaaaaaa"):
        return DeviceToken.objects.create(user=user or self.user, token=token)

    def set_user(self, user=None, **fields):
        user = user or self.user
        User.objects.filter(pk=user.pk).update(**fields)
        user.refresh_from_db()
        return user


# ==monthly reminder==
class ReminderScheduleTests(Base):
    def test_due_on_the_chosen_day_after_the_chosen_time_only(self):
        self.make_avatar()
        self.set_user(reminder_day=15, reminder_time=time(10, 0))
        self.assertEqual(users_due_for_reminder(NOW), [self.user])
        self.assertEqual(users_due_for_reminder(NOW.replace(hour=7, minute=59)), [])
        self.assertEqual(users_due_for_reminder(NOW.replace(hour=8, minute=0)), [self.user])
        self.assertEqual(users_due_for_reminder(NOW - timedelta(days=1)), [])

    def test_the_users_own_time_zone_decides(self):
        self.make_avatar()
        self.set_user(reminder_day=15, reminder_time=time(10, 0), timezone_name="America/New_York")
        self.assertEqual(users_due_for_reminder(NOW), [])
        self.assertEqual(users_due_for_reminder(NOW.replace(hour=16)), [self.user])

    def test_an_unknown_stored_zone_falls_back_instead_of_crashing(self):
        self.make_avatar()
        self.set_user(reminder_day=15, timezone_name="Mars/Phobos")
        self.assertEqual(users_due_for_reminder(NOW), [self.user])

    def test_catches_up_after_downtime_but_only_once_per_month(self):
        self.make_avatar()
        self.set_user(reminder_day=1)
        self.assertEqual(send_due_reminders(NOW), 1)
        self.assertEqual(send_due_reminders(NOW + timedelta(hours=1)), 0)
        self.assertEqual(send_due_reminders(NOW + timedelta(days=10)), 0)
        december = NOW + timedelta(days=20)
        self.assertEqual(send_due_reminders(december), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_the_month_is_counted_in_the_users_zone(self):
        self.make_avatar()
        self.set_user(reminder_day=1, last_reminder_at=datetime(2026, 11, 30, 23, 30, tzinfo=dt_timezone.utc))
        self.assertEqual(users_due_for_reminder(datetime(2026, 12, 1, 9, 0, tzinfo=dt_timezone.utc)), [])

    def test_fresh_measurements_skip_the_reminder(self):
        self.set_user(reminder_day=1)
        a = self.make_avatar(days_old=5)
        self.assertEqual(users_due_for_reminder(NOW), [])
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=NOW - timedelta(days=13, hours=23))
        self.assertEqual(users_due_for_reminder(NOW), [])
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=NOW - timedelta(days=14))
        self.assertEqual(users_due_for_reminder(NOW), [self.user])

    def test_the_newest_update_of_any_avatar_counts(self):
        self.set_user(reminder_day=1)
        self.make_avatar(days_old=90, is_default=False)
        self.make_avatar(days_old=3)
        self.assertEqual(users_due_for_reminder(NOW), [])

    def test_several_old_avatars_make_one_reminder(self):
        self.set_user(reminder_day=1)
        self.make_avatar(days_old=60, is_default=False)
        self.make_avatar(days_old=45)
        self.assertEqual(send_due_reminders(NOW), 1)

    def test_at_least_twenty_days_between_reminders(self):
        self.make_avatar()
        self.set_user(reminder_day=1, last_reminder_at=NOW - timedelta(days=19))
        self.assertEqual(users_due_for_reminder(NOW), [])
        self.set_user(last_reminder_at=NOW - timedelta(days=21))
        self.assertEqual(users_due_for_reminder(NOW + timedelta(days=20)), [self.user])

    def test_opt_out_inactive_and_users_without_avatars_are_skipped(self):
        self.make_avatar()
        self.set_user(reminder_day=1, reminder_enabled=False)
        self.assertEqual(users_due_for_reminder(NOW), [])
        self.set_user(reminder_enabled=True, is_active=False)
        self.assertEqual(users_due_for_reminder(NOW), [])
        self.set_user(is_active=True)
        self.assertEqual(send_due_reminders(NOW), 1)

    def test_reminder_due_is_a_pure_function_of_its_inputs(self):
        self.set_user(reminder_day=15)
        self.assertTrue(reminder_due(self.user, None, NOW))
        self.assertFalse(reminder_due(self.user, NOW - timedelta(days=1), NOW))


class ReminderDeliveryTests(Base):
    def setUp(self):
        super().setUp()
        self.make_avatar()
        self.set_user(reminder_day=1)
        self.device()

    def test_card_and_push_with_an_action_for_the_app(self):
        self.assertEqual(send_due_reminders(NOW), 1)
        n = Notification.objects.get()
        self.assertEqual((n.kind, n.action, n.data), ("measurement_reminder", "update_measurements",
                                                      {"avatar_id": str(Avatar.objects.get().pk)}))
        self.assertTrue(n.title.startswith("Час оновити"))
        call = RecordingPush.calls[0]
        self.assertEqual((call["tokens"], call["data"]["kind"], call["data"]["notification_id"]),
                         (["fcm-token-aaaaaaaa"], "measurement_reminder", n.pk))
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_reminder_at, NOW)

    def test_language(self):
        self.set_user(language="en")
        send_due_reminders(NOW)
        self.assertTrue(Notification.objects.get().title.startswith("Time to update"))

    def test_the_two_channel_switches_of_the_profile_screen(self):
        self.set_user(push_enabled=False)
        send_due_reminders(NOW)
        self.assertEqual((Notification.objects.count(), len(RecordingPush.calls)), (1, 0))
        Notification.objects.all().delete()
        self.set_user(push_enabled=True, in_app_enabled=False, last_reminder_at=None)
        send_due_reminders(NOW)
        self.assertEqual((Notification.objects.count(), len(RecordingPush.calls)), (0, 1))
        self.assertNotIn("notification_id", RecordingPush.calls[0]["data"])

    def test_with_both_channels_off_nothing_is_sent_and_nothing_is_marked(self):
        self.set_user(push_enabled=False, in_app_enabled=False)
        self.assertEqual(send_due_reminders(NOW), 0)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.last_reminder_at)
        self.set_user(in_app_enabled=True)
        self.assertEqual(send_due_reminders(NOW), 1)

    def test_management_command(self):
        out = StringIO()
        with mock.patch("notifications.services.timezone.now", return_value=NOW):
            call_command("send_measurement_reminders", stdout=out)
        self.assertIn("Sent 1", out.getvalue())


# ==delivery rules==
class NotifyTests(Base):
    def test_in_app_push_both_none(self):
        self.device()
        cases = [(True, True, 1, 1), (True, False, 1, 0), (False, True, 0, 1), (False, False, 0, 0)]
        for in_app, push, cards, pushes in cases:
            Notification.objects.all().delete()
            RecordingPush.calls = []
            self.set_user(in_app_enabled=in_app, push_enabled=push)
            note = notify(self.user, Kind.AVATAR_READY, "t", "b", "open_avatar", {"avatar_id": "x"})
            self.assertEqual((Notification.objects.count(), len(RecordingPush.calls), note is not None),
                             (cards, pushes, bool(cards)), (in_app, push))

    def test_a_user_without_devices_gets_no_push_and_no_error(self):
        notify(self.user, Kind.AVATAR_READY, "t", "b")
        self.assertEqual(RecordingPush.calls, [])

    def test_all_phones_of_the_user_get_the_message_and_dead_tokens_are_removed(self):
        self.device(token="fcm-token-good-1")
        self.device(token="fcm-token-dead-2")
        self.device(user=self.other, token="fcm-token-bobs-3")
        RecordingPush.invalid = ["fcm-token-dead-2"]
        notify(self.user, Kind.AVATAR_READY, "t", "b")
        self.assertEqual(sorted(RecordingPush.calls[0]["tokens"]), ["fcm-token-dead-2", "fcm-token-good-1"])
        self.assertEqual(set(DeviceToken.objects.values_list("token", flat=True)),
                         {"fcm-token-good-1", "fcm-token-bobs-3"})

    @override_settings(PUSH_BACKEND="notifications.tests.ExplodingPush")
    def test_a_push_failure_never_breaks_the_caller(self):
        self.device()
        with self.assertLogs("notifications.services", level="ERROR"):
            note = notify(self.user, Kind.AVATAR_READY, "t", "b")
        self.assertIsNotNone(note)

    @override_settings(PUSH_BACKEND="notifications.push.NullPushBackend")
    def test_the_default_backend_delivers_nothing(self):
        self.device()
        self.assertIsNotNone(notify(self.user, Kind.AVATAR_READY, "t", "b"))
        self.assertEqual(RecordingPush.calls, [])

    def test_the_setting_is_optional(self):
        from django.conf import settings
        self.device()
        with override_settings():
            del settings.PUSH_BACKEND
            self.assertIsNotNone(notify(self.user, Kind.AVATAR_READY, "t", "b"))


# ==avatar ready==
_TMP = Path(tempfile.mkdtemp(prefix="vertex-notif-media-"))


@override_settings(MEDIA_ROOT=_TMP, FILE_ENCRYPTION_KEY=Fernet.generate_key().decode(), AVATAR_GENERATION_EAGER=True)
class AvatarReadyTests(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_TMP, ignore_errors=True)

    def generate(self, avatar):
        from avatars.services.generator import start_generation
        start_generation(avatar)

    def test_finishing_the_model_creates_a_card_and_a_push(self):
        a = self.make_avatar()
        self.device()
        self.generate(a)
        n = Notification.objects.get()
        self.assertEqual((n.kind, n.action, n.data, n.title), ("avatar_ready", "open_avatar", {"avatar_id": str(a.pk)},
                                                               "Аватар «Main» готовий"))
        self.assertEqual(RecordingPush.calls[0]["data"]["action"], "open_avatar")

    def test_english_text_and_the_channel_switch(self):
        a = self.make_avatar()
        self.set_user(language="en", in_app_enabled=False, push_enabled=False)
        self.generate(a)
        self.assertEqual(Notification.objects.count(), 0)
        self.set_user(in_app_enabled=True)
        self.generate(a)
        self.assertEqual(Notification.objects.get().title, "Avatar “Main” is ready")

    def test_a_failed_generation_sends_nothing(self):
        a = self.make_avatar()
        with mock.patch("avatars.services.generator.compute_morph_params", side_effect=RuntimeError("boom")), \
                self.assertLogs("avatars.services.generator", level="ERROR"):
            self.generate(a)
        self.assertEqual(Notification.objects.count(), 0)

    def test_a_cancelled_run_sends_nothing(self):
        from uuid import uuid4
        from avatars.services.generator import cancel_generation, run_generation
        a = self.make_avatar()
        run = uuid4()
        Avatar.objects.filter(pk=a.pk).update(status="processing", generation_run=run)
        cancel_generation(Avatar.objects.get(pk=a.pk))
        run_generation(a.pk, run)
        self.assertEqual(Notification.objects.count(), 0)

    def test_a_broken_notification_does_not_fail_the_avatar(self):
        a = self.make_avatar()
        with mock.patch("notifications.services.notify_avatar_ready", side_effect=RuntimeError("oops")), \
                self.assertLogs("avatars.services.generator", level="ERROR"):
            self.generate(a)
        self.assertEqual(Avatar.objects.get(pk=a.pk).status, "ready")


# ==price drops==
class PriceDropTests(Base):
    def setUp(self):
        super().setUp()
        cat = Category.objects.create(slug="hoodies", name_uk="Худі", name_en="Hoodies")
        self.product = Product.objects.create(brand=Brand.objects.create(name="Urban Co"), category=cat,
                                              title="Oversize Hoodie", price=Decimal("1500"))
        ProductSize.objects.create(product=self.product, label="M", order=0, chest_min=92, chest_max=100)
        self.avatar = self.make_avatar()

    def put_on(self, user, size="M"):
        session = TryOnSession.objects.create(user=user, avatar=Avatar.objects.get(user=user)
                                              if Avatar.objects.filter(user=user).exists() else self.avatar)
        TryOnItem.objects.create(session=session, product=self.product, size_label=size)

    def test_only_people_who_tried_the_item_are_told(self):
        self.put_on(self.user)
        notified = notify_price_drops([(self.product, Decimal("1500"), Decimal("1200"))], NOW)
        self.assertEqual(notified, 1)
        n = Notification.objects.get()
        self.assertEqual((n.user, n.kind, n.action, n.data), (self.user, "price_drop", "open_product",
                                                              {"product_id": self.product.pk}))
        self.assertEqual(n.title, "Знижка −20%: Oversize Hoodie")
        self.assertEqual(n.body, "Було 1500, стало 1200 UAH. Ваш розмір: M.")
        self.assertFalse(Notification.objects.filter(user=self.other).exists())

    def test_english_text(self):
        self.set_user(language="en")
        self.put_on(self.user, "L")
        notify_price_drops([(self.product, Decimal("200"), Decimal("150"))], NOW)
        n = Notification.objects.get()
        self.assertEqual((n.title, n.body), ("25% off: Oversize Hoodie", "Was 200, now 150 UAH. Your size: L."))

    def test_no_drop_no_message(self):
        self.put_on(self.user)
        for old, new in ((1500, 1500), (1500, 1800), (None, 100), (1500, None)):
            drops = [(self.product, Decimal(old) if old else None, Decimal(new) if new else None)]
            self.assertEqual(notify_price_drops(drops, NOW), 0, (old, new))

    def test_once_a_week_per_user_and_product(self):
        self.put_on(self.user)
        drop = [(self.product, Decimal("1500"), Decimal("1200"))]
        self.assertEqual(notify_price_drops(drop, NOW), 1)
        self.assertEqual(notify_price_drops(drop, NOW + timedelta(days=1)), 0)
        Notification.objects.update(created_at=NOW - timedelta(days=8))
        self.assertEqual(notify_price_drops(drop, NOW), 1)

    def test_a_user_with_two_sessions_gets_one_message(self):
        self.put_on(self.user)
        self.put_on(self.user)
        self.assertEqual(notify_price_drops([(self.product, Decimal("1500"), Decimal("1200"))], NOW), 1)

    def test_inactive_users_and_disabled_channels(self):
        self.put_on(self.user)
        self.set_user(is_active=False)
        self.assertEqual(notify_price_drops([(self.product, Decimal("1500"), Decimal("1200"))], NOW), 0)
        self.set_user(is_active=True, in_app_enabled=False, push_enabled=False)
        notify_price_drops([(self.product, Decimal("1500"), Decimal("1200"))], NOW)
        self.assertEqual(Notification.objects.count(), 0)

    def test_the_bulk_import_reports_drops_and_the_command_announces_them(self):
        from catalog.importing import import_catalog
        self.put_on(self.user)
        item = {"brand": "Urban Co", "title": "Oversize Hoodie", "category": "hoodies", "gender": "unisex",
                "use_default_chart": True}
        report = import_catalog({"products": [{**item, "price": 1200}]})
        self.assertEqual([(p.pk, old, new) for p, old, new in report.price_drops],
                         [(self.product.pk, Decimal("1500.00"), Decimal("1200.00"))])
        self.assertEqual(import_catalog({"products": [{**item, "price": 1200}]}).price_drops, [])
        self.assertEqual(import_catalog({"products": [{**item, "price": 1900}]}).price_drops, [])
        self.assertEqual(import_catalog({"products": [{**item}]}).price_drops, [])

    def test_import_command_notifies_after_committing_but_not_in_dry_run(self):
        import json
        self.put_on(self.user)
        data = {"products": [{"brand": "Urban Co", "title": "Oversize Hoodie", "category": "hoodies",
                              "gender": "unisex", "use_default_chart": True, "price": 1200}]}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            out = StringIO()
            call_command("import_catalog", str(path), "--dry-run", stdout=out)
            self.assertEqual(Notification.objects.count(), 0)
            self.assertIn("would be announced", out.getvalue())
            out = StringIO()
            call_command("import_catalog", str(path), stdout=out)
        self.assertIn("1 user(s) notified", out.getvalue())
        self.assertEqual(Notification.objects.get().kind, "price_drop")


# ==weekly digest==
class DigestTests(Base):
    def setUp(self):
        super().setUp()
        self.cat = Category.objects.create(slug="tshirts", name_uk="Футболки", name_en="T-shirts")
        self.brand = Brand.objects.create(name="B")
        self.make_avatar()

    def add_product(self, title, days_old=2, gender="unisex", owner=None, chest=(92, 100)):
        p = Product.objects.create(brand=self.brand, category=self.cat, title=title, gender=gender, owner=owner)
        ProductSize.objects.create(product=p, label="M", order=0, chest_min=chest[0], chest_max=chest[1],
                                   waist_min=78, waist_max=86, hips_min=96, hips_max=102)
        Product.objects.filter(pk=p.pk).update(created_at=NOW - timedelta(days=days_old))
        return p

    def test_sent_when_enough_new_items_match_very_well(self):
        for i in range(3):
            self.add_product(f"New {i}")
        self.assertEqual(send_new_collection_digests(NOW), 1)
        n = Notification.objects.get()
        self.assertEqual((n.kind, n.action, n.data), ("new_collection", "open_catalog",
                                                      {"min_compat": 95, "ordering": "new"}))
        self.assertIn("3", n.title)

    def test_not_enough_old_foreign_private_or_poorly_fitting_items_do_not_count(self):
        self.add_product("New 1")
        self.add_product("New 2")
        self.add_product("Old", days_old=10)
        self.add_product("Private", owner=self.other)
        self.add_product("Hers", gender="female")
        self.add_product("Too big", chest=(120, 130))
        self.assertEqual(send_new_collection_digests(NOW), 0)
        self.add_product("New 3")
        self.assertEqual(send_new_collection_digests(NOW), 1)

    def test_weekly_cooldown_and_channel_switches(self):
        for i in range(3):
            self.add_product(f"New {i}")
        self.assertEqual(send_new_collection_digests(NOW), 1)
        self.assertEqual(send_new_collection_digests(NOW + timedelta(days=3)), 0)
        Notification.objects.update(created_at=NOW - timedelta(days=7))
        self.set_user(in_app_enabled=False, push_enabled=False)
        self.assertEqual(send_new_collection_digests(NOW), 0)
        self.set_user(push_enabled=True)
        self.device()
        self.assertEqual(send_new_collection_digests(NOW), 1)
        self.assertEqual(RecordingPush.calls[0]["data"]["kind"], "new_collection")

    def test_users_without_a_default_avatar_are_skipped_and_the_command_runs(self):
        for i in range(3):
            self.add_product(f"New {i}")
        Avatar.objects.all().delete()
        self.assertEqual(send_new_collection_digests(NOW), 0)
        self.make_avatar()
        out = StringIO()
        with mock.patch("notifications.services.timezone.now", return_value=NOW):
            call_command("send_new_collection_digests", stdout=out)
        self.assertIn("Sent 1", out.getvalue())


# ==API==
class NotificationApiTests(Base):
    def make_notes(self, user, n=1, **extra):
        return [Notification.objects.create(user=user, kind="measurement_reminder", title=f"t{i}", body="b", **extra)
                for i in range(n)]

    def test_list_is_private_newest_first_with_unread_count_and_actions(self):
        mine = self.make_notes(self.user, 2, action="update_measurements", data={"avatar_id": "a1"})
        self.make_notes(self.other, 3)
        r = self.client.get(reverse("notifications"))
        self.assertEqual([n["id"] for n in r.data["results"]], [mine[1].pk, mine[0].pk])
        self.assertEqual(r.data["unread_count"], 2)
        first = r.data["results"][0]
        self.assertEqual((first["action"], first["data"], first["kind"]), ("update_measurements", {"avatar_id": "a1"},
                                                                          "measurement_reminder"))

    def test_same_timestamp_does_not_make_the_order_random(self):
        notes = self.make_notes(self.user, 5)
        Notification.objects.update(created_at=timezone.now())
        for _ in range(3):
            ids = [n["id"] for n in self.client.get(reverse("notifications")).data["results"]]
            self.assertEqual(ids, sorted((n.pk for n in notes), reverse=True))

    def test_unread_filter(self):
        a, b = self.make_notes(self.user, 2)
        self.client.post(reverse("notification-read", args=[a.pk]))
        ids = [n["id"] for n in self.client.get(reverse("notifications"), {"unread": "true"}).data["results"]]
        self.assertEqual(ids, [b.pk])
        self.assertEqual(len(self.client.get(reverse("notifications")).data["results"]), 2)

    def test_mark_one_and_mark_all(self):
        a, b = self.make_notes(self.user, 2)
        self.assertEqual(self.client.post(reverse("notification-read", args=[a.pk])).data["updated"], 1)
        self.assertEqual(self.client.get(reverse("notifications")).data["unread_count"], 1)
        self.assertEqual(self.client.post(reverse("notifications-read-all")).data["updated"], 1)
        self.assertEqual(self.client.post(reverse("notifications-read-all")).data["updated"], 0)
        self.assertEqual(self.client.get(reverse("notifications")).data["unread_count"], 0)

    def test_other_users_notifications_cannot_be_touched(self):
        theirs = self.make_notes(self.other)[0]
        self.assertEqual(self.client.post(reverse("notification-read", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("notifications-read-all")).data["updated"], 0)
        theirs.refresh_from_db()
        self.assertFalse(theirs.read)

    def test_pagination(self):
        self.make_notes(self.user, 25)
        r = self.client.get(reverse("notifications"))
        self.assertEqual((len(r.data["results"]), r.data["count"]), (20, 25))
        self.assertEqual(len(self.client.get(reverse("notifications"), {"page": 2}).data["results"]), 5)

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(reverse("notifications")).status_code, 401)
        self.assertEqual(self.client.post(reverse("notifications-read-all")).status_code, 401)

    def test_deleting_the_account_removes_notifications_and_devices(self):
        self.make_notes(self.user, 2)
        self.device()
        self.client.delete(reverse("me"))
        self.assertEqual((Notification.objects.count(), DeviceToken.objects.count()), (0, 0))


class DeviceApiTests(Base):
    TOKEN = "fcm-token-1234567890"

    def post(self, **data):
        return self.client.post(reverse("devices"), {"token": self.TOKEN, **data}, format="json")

    def test_register_refresh_and_platform(self):
        r = self.post()
        self.assertEqual((r.status_code, r.data), (201, {"registered": True}))
        self.assertEqual(DeviceToken.objects.get().platform, "android")
        self.assertEqual(self.post(platform="ios").status_code, 200)
        self.assertEqual((DeviceToken.objects.count(), DeviceToken.objects.get().platform), (1, "ios"))

    def test_a_phone_that_switches_account_follows_the_new_user(self):
        self.post()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(DeviceToken.objects.get().user, self.other)

    def test_validation(self):
        for bad in ({"token": "short"}, {"token": ""}, {"platform": "windows"}, {"token": "x" * 4097}):
            self.assertEqual(self.post(**bad).status_code, 400, bad)
        self.assertEqual(self.client.post(reverse("devices"), {}, format="json").status_code, 400)

    def test_at_most_ten_devices_per_user_oldest_dropped(self):
        for i in range(12):
            self.client.post(reverse("devices"), {"token": f"fcm-token-device-{i:02d}"}, format="json")
        tokens = set(DeviceToken.objects.filter(user=self.user).values_list("token", flat=True))
        self.assertEqual(len(tokens), 10)
        self.assertIn("fcm-token-device-11", tokens)
        self.assertNotIn("fcm-token-device-00", tokens)

    def test_delete_own_token_and_never_someone_elses(self):
        self.post()
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(reverse("devices"), {"token": self.TOKEN}, format="json").status_code, 204)
        self.assertEqual(DeviceToken.objects.count(), 1)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(reverse("devices"), {"token": self.TOKEN}, format="json").status_code, 204)
        self.assertEqual(DeviceToken.objects.count(), 0)
        self.assertEqual(self.client.delete(reverse("devices"), {"token": self.TOKEN}, format="json").status_code, 204)

    def test_logout_forgets_this_phones_token(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        self.post()
        self.device(token="fcm-token-other-phone")
        refresh = str(RefreshToken.for_user(self.user))
        r = self.client.post(reverse("logout"), {"refresh": refresh, "device_token": self.TOKEN}, format="json")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(list(DeviceToken.objects.values_list("token", flat=True)), ["fcm-token-other-phone"])

    def test_requires_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.post().status_code, 401)