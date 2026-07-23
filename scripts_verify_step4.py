import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import User
from donors import services
from donors.models import Donor, ScreeningRecord

settings.ALLOWED_HOSTS.append("testserver")

donor = Donor.objects.get(user__username="verify_donor")
ScreeningRecord.objects.filter(donor=donor).delete()

# stage 1 auto-pass for healthy adult
passed, reasons, permanent = services.run_stage1(donor)
assert passed, reasons
print("stage 1 pass OK")

# service-level boundary spot checks
import datetime

from django.utils import timezone

today = timezone.localdate()
donor.date_of_birth = today.replace(year=today.year - 17)
passed, reasons, permanent = services.run_stage1(donor)
assert not passed and not permanent
donor.date_of_birth = datetime.date(1995, 5, 10)

donor.weight_kg = 49.9
passed, reasons, _ = services.run_stage1(donor)
assert not passed
donor.weight_kg = 70.5
print("stage 1 failure boundaries OK")

# stage 2
ok, reasons = services.run_stage2(12.4, 120, 80)
assert not ok
ok, reasons = services.run_stage2(12.5, 120, 80)
assert ok
ok, reasons = services.run_stage2(13.0, 185, 80)
assert not ok
print("stage 2 thresholds OK")

# staff runs screening via view
c = Client()
staff = User.objects.get(username="verify_staff")
c.force_login(staff)
r = c.get("/donors/screening/")
assert r.status_code == 200 and b"Verify Donor" in r.content
r = c.get(f"/donors/screening/{donor.pk}/")
assert r.status_code == 200 and b"Passed" in r.content
r = c.post(f"/donors/screening/{donor.pk}/", {"hemoglobin_g_dl": "13.5", "systolic_bp": "120", "diastolic_bp": "80"})
assert r.status_code == 302, r.status_code
rec = services.latest_screening(donor)
assert rec.outcome == "ELIGIBLE" and rec.stage1_passed
print("staff screening ELIGIBLE OK")

ok, why = services.can_donate(donor)
assert ok, why
print("can_donate true after eligible screening")

# blocked when screening deferred
r = c.post(f"/donors/screening/{donor.pk}/", {"hemoglobin_g_dl": "11.0", "systolic_bp": "120", "diastolic_bp": "80"})
rec = services.latest_screening(donor)
assert rec.outcome == "TEMP_DEFERRED"
ok, why = services.can_donate(donor)
assert not ok
print("can_donate blocked on TEMP_DEFERRED:", why)

# donor sees eligibility on dashboard
c.force_login(donor.user)
r = c.get("/accounts/dashboard/")
assert r.status_code == 200 and b"appears eligible" in r.content.lower() or b"appear eligible" in r.content
print("donor dashboard eligibility panel OK")

# role gate: donor cannot open screening pages
r = c.get("/donors/screening/")
assert r.status_code == 403
print("screening role gate OK")

# restore an ELIGIBLE screening for later steps
services.screen_donor(donor, 13.5, 120, 80)
print("STEP 4 VERIFIED")
