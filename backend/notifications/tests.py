from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from avatars.models import Avatar

from .models import Notification
from .services import send_due_reminders, users_due_for_reminder

PASSWORD = "S3cure-pass-word"
BODY = {"chest_circumference": 96, "waist_circumference": 82, "hip_circumference": 100}


class NotificationBase(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("alice@example.com", PASSWORD, username="Alice", gender="female")
        self.other = User.objects.create_user("bob@example.com", PASSWORD, username="Bob", gender="male")
        self.client.force_authenticate(self.user)

    def make_avatar(self, user=None, days_old=0, **over):
        a = Avatar.objects.create(user=user or self.user, name="Me", gender="female", age=25, height_cm=170,
                                  weight_kg=60, measurements=dict(BODY), **over)
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=timezone.now() - timedelta(days=days_old))
        return a


class ReminderLogicTests(NotificationBase):
    def test_due_only_after_a_month(self):
        self.make_avatar(days_old=10)
        self.assertEqual(list(users_due_for_reminder()), [])
        Avatar.objects.update(measurements_updated_at=timezone.now() - timedelta(days=31))
        self.assertEqual(list(users_due_for_reminder()), [self.user])

    def test_the_newest_measurement_update_counts(self):
        self.make_avatar(days_old=90)
        self.make_avatar(days_old=3)
        self.assertEqual(list(users_due_for_reminder()), [])

    def test_user_with_several_old_avatars_is_listed_once(self):
        self.make_avatar(days_old=60)
        self.make_avatar(days_old=45)
        self.assertEqual(list(users_due_for_reminder()), [self.user])

    def test_opt_out_inactive_and_users_without_avatars_are_skipped(self):
        self.make_avatar(days_old=60)
        User.objects.filter(pk=self.user.pk).update(reminder_enabled=False)
        self.assertEqual(list(users_due_for_reminder()), [])
        User.objects.filter(pk=self.user.pk).update(reminder_enabled=True, is_active=False)
        self.assertEqual(list(users_due_for_reminder()), [])
        User.objects.filter(pk=self.user.pk).update(is_active=True)
        self.assertEqual(list(users_due_for_reminder()), [self.user])
        self.assertEqual(send_due_reminders(), 1)

    def test_sent_once_per_cycle_then_again_next_month(self):
        self.make_avatar(days_old=45)
        self.assertEqual(send_due_reminders(), 1)
        self.assertEqual(send_due_reminders(), 0)
        self.assertEqual(send_due_reminders(now=timezone.now() + timedelta(days=31)), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_message_follows_the_users_language(self):
        self.make_avatar(days_old=45)
        self.make_avatar(user=self.other, days_old=45)
        User.objects.filter(pk=self.user.pk).update(language="en")
        send_due_reminders()
        self.assertTrue(Notification.objects.get(user=self.user).title.startswith("Time to update"))
        self.assertTrue(Notification.objects.get(user=self.other).title.startswith("Час оновити"))

    def test_updating_measurements_resets_the_cycle(self):
        a = self.make_avatar(days_old=45)
        Avatar.objects.filter(pk=a.pk).update(measurements_updated_at=timezone.now())
        self.assertEqual(send_due_reminders(), 0)

    def test_management_command(self):
        self.make_avatar(days_old=40)
        out = StringIO()
        call_command("send_measurement_reminders", stdout=out)
        self.assertIn("Sent 1", out.getvalue())


class NotificationApiTests(NotificationBase):
    def make_notes(self, user, n=1):
        return [Notification.objects.create(user=user, kind="measurement_reminder", title=f"t{i}", body="b")
                for i in range(n)]

    def test_list_is_private_newest_first_with_unread_count(self):
        mine = self.make_notes(self.user, 2)
        self.make_notes(self.other, 3)
        r = self.client.get(reverse("notifications"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([n["id"] for n in r.data["results"]], [mine[1].pk, mine[0].pk])
        self.assertEqual(r.data["unread_count"], 2)

    def test_mark_one_and_mark_all(self):
        a, b = self.make_notes(self.user, 2)
        r = self.client.post(reverse("notification-read", args=[a.pk]))
        self.assertEqual(r.data["updated"], 1)
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

    def test_deleting_the_account_removes_notifications(self):
        self.make_notes(self.user, 2)
        self.client.delete(reverse("me"))
        self.assertEqual(Notification.objects.count(), 0)