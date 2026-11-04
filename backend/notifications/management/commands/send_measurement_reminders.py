from django.core.management.base import BaseCommand

from notifications.services import send_due_reminders


class Command(BaseCommand):
    help = "Send monthly measurement-update reminders. Run daily from cron / Celery beat."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_due_reminders()} reminders.")