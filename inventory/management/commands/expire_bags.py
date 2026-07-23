"""Daily-runnable command: mark past-expiry bags EXPIRED (audited, triggers low-stock checks)."""
from django.core.management.base import BaseCommand

from inventory.services import expire_past_due_bags


class Command(BaseCommand):
    help = "Mark blood bags past their expiry date as EXPIRED."

    def handle(self, *args, **options):
        n = expire_past_due_bags()
        self.stdout.write(self.style.SUCCESS(f"Expired {n} bag(s)."))
