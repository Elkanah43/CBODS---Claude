"""Auto-lift expired temporary deferrals; notify donors/staff."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from donors.models import Deferral
from donors.services import get_active_deferrals
from notifications.services import notify


class Command(BaseCommand):
    help = "Auto-lift expired temporary deferrals and re-enable eligible donors."

    def handle(self, *args, **options):
        today = timezone.localdate()
        expired = Deferral.objects.filter(
            is_permanent=False, end_date__lt=today, lifted_at__isnull=True
        )
        count = 0
        for d in expired:
            d.lifted_by = None  # system
            d.lifted_at = timezone.now()
            d.lifted_reason = "Auto-expired"
            d.save(update_fields=["lifted_by", "lifted_at", "lifted_reason"])
            # Re-check donor availability
            if not get_active_deferrals(d.donor).exists():
                d.donor.is_available = True
                d.donor.save(update_fields=["is_available"])
                notify(
                    d.donor.user,
                    "Deferral period ended",
                    "Your temporary deferral has expired. You may now be eligible to donate again. "
                    "Log in to check your status and book an appointment.",
                )
            count += 1
        self.stdout.write(self.style.SUCCESS(f"Auto-lifted {count} expired deferral(s)."))