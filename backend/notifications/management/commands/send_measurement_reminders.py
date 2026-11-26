from django.core.management.base import BaseCommand

from notifications.services import send_due_reminders


class Command(BaseCommand):
    help = "Send the monthly measurement-update reminders that are due. Run HOURLY (the day and time are per user)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_due_reminders()} reminders.")