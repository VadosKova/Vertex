from django.core.management.base import BaseCommand

from notifications.services import send_new_collection_digests


class Command(BaseCommand):
    help = "Weekly 'new selection for you' notifications. Run once a week (e.g. Monday morning)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_new_collection_digests()} digests.")