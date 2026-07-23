import datetime
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from accounts.models import User
from audit.models import AuditLog
from donors.models import Donor
from inventory.models import BagStatus, BloodBag, Donation
from inventory.services import stock_by_group
from notifications.models import Notification

settings.ALLOWED_HOSTS.append("testserver")

staff = User.objects.get(username="verify_staff")
donor = Donor.objects.get(user__username="verify_donor")
hospital = staff.staff_profile.hospital

# clean slate for this hospital
BloodBag.objects.filter(hospital=hospital).delete()
Donation.objects.filter(hospital=hospital).delete()

c = Client()
c.force_login(staff)

r = c.get("/inventory/stock/")
assert r.status_code == 200
print("stock dashboard loads")

# record donation via view (donor has ELIGIBLE screening from step 4)
r = c.post("/inventory/donate/", {"donor": donor.pk, "volume_ml": 450})
assert r.status_code == 302, r.content[:300]
don = Donation.objects.get(donor=donor, hospital=hospital)
bag = BloodBag.objects.get(donation=don)
assert bag.status == "AVAILABLE" and bag.blood_group == donor.blood_group
assert bag.expiry_date == bag.collected_date + datetime.timedelta(days=35)
assert AuditLog.objects.filter(action="BAG_CREATED", entity_id=str(bag.pk)).exists()
print("donation recorded, bag AVAILABLE, expiry +35d, audit OK")

# computed stock
stock = stock_by_group(hospital)
assert stock[donor.blood_group] == 1
print("computed stock OK:", {k: v for k, v in stock.items() if v})

# donation blocking: immediate second donation must fail (interval + stale screening)
r = c.post("/inventory/donate/", {"donor": donor.pk, "volume_ml": 450})
assert r.status_code == 200 and b"Donation blocked" in r.content
assert Donation.objects.filter(donor=donor).count() == 1
print("second donation blocked OK")

# expiry command: create a past-expiry bag then run command
old = BloodBag.objects.create(
    hospital=hospital, blood_group="B+", volume_ml=450,
    collected_date=timezone.localdate() - datetime.timedelta(days=40),
    expiry_date=timezone.localdate() - datetime.timedelta(days=5),
)
Notification.objects.all().delete()
call_command("expire_bags")
old.refresh_from_db()
assert old.status == "EXPIRED"
assert AuditLog.objects.filter(action="BAG_EXPIRED", entity_id=str(old.pk)).exists()
# low stock notification fired for B+ (0 left < 3) to hospital staff
assert Notification.objects.filter(user=staff, subject__icontains="Low stock: B+").exists()
print("expire_bags command + audit + low-stock notification OK")

# near-expiry flag appears on dashboard
soon = BloodBag.objects.create(
    hospital=hospital, blood_group="A+", volume_ml=450,
    collected_date=timezone.localdate() - datetime.timedelta(days=30),
    expiry_date=timezone.localdate() + datetime.timedelta(days=3),
)
r = c.get("/inventory/stock/")
assert b"Expiring soon" in r.content
print("near-expiry flag OK")

# role gate
c.force_login(donor.user)
r = c.get("/inventory/stock/")
assert r.status_code == 403
print("inventory role gate OK")

print("STEP 5 VERIFIED")
