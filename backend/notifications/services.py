from datetime import timedelta

from django.conf import settings
from django.db.models import Max, Q
from django.utils import timezone

from accounts.models import User

from .models import Notification

TEXT = {
    "uk": ("Час оновити заміри", "Ваші параметри не оновлювались понад місяць. Оновіть їх для точної примірки."),
    "en": ("Time to update your measurements", "Your measurements haven't been updated for over a month. Update them for accurate fitting."),
}


def reminder_cutoff(now=None):
    days = getattr(settings, "MEASUREMENT_REMINDER_DAYS", 30)
    return (now or timezone.now()) - timedelta(days=days)


def users_due_for_reminder(now=None):
    cutoff = reminder_cutoff(now)
    return (User.objects.filter(is_active=True, reminder_enabled=True, avatars__isnull=False)
            .annotate(last_measured=Max("avatars__measurements_updated_at"))
            .filter(last_measured__lte=cutoff)
            .filter(Q(last_reminder_at__isnull=True) | Q(last_reminder_at__lte=cutoff)))


def send_push(user, title, body):
    return False


def send_due_reminders(now=None):
    now = now or timezone.now()
    count = 0
    for user in users_due_for_reminder(now):
        title, body = TEXT.get(user.language, TEXT["uk"])
        Notification.objects.create(user=user, kind=Notification.Kind.MEASUREMENT_REMINDER, title=title, body=body)
        send_push(user, title, body)
        user.last_reminder_at = now
        user.save(update_fields=["last_reminder_at"])
        count += 1
    return count