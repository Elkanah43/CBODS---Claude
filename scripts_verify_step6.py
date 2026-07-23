import datetime
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client
from django.utils import timezone

from accounts.models import Role, User
from audit.models import AuditLog
from hospitals.models import Hospital
from inventory.models import BagStatus, BloodBag
from requests_app.models import BloodRequest
from requests_app import services

settings.ALLOWED_HOSTS.append("testserver")

staff = User.objects.get(username="verify_staff")
hospital = staff.staff_profile.hospital
hidden = Hospital.objects.get(name="Verify Hidden")

patient, _ = User.objects.get_or_create(username="verify_patient", defaults={"role": Role.PATIENT, "email": "vp@example.com"})
patient.role = Role.PATIENT
patient.save()

# stock: three O+ bags with staggered expiry for FEFO check
BloodBag.objects.filter(hospital=hospital).delete()
BloodRequest.objects.filter(hospital=hospital).delete()
today = timezone.localdate()
b_late = BloodBag.objects.create(hospital=hospital, blood_group="O+", collected_date=today, expiry_date=today + datetime.timedelta(days=30))
b_soon = BloodBag.objects.create(hospital=hospital, blood_group="O+", collected_date=today, expiry_date=today + datetime.timedelta(days=5))
b_mid = BloodBag.objects.create(hospital=hospital, blood_group="O+", collected_date=today, expiry_date=today + datetime.timedelta(days=15))

c = Client()
c.force_login(patient)

# hidden hospital invisible
r = c.get("/requests/hospitals/")
assert r.status_code == 200
assert hospital.name.encode() in r.content and b"Verify Hidden" not in r.content
print("hospital list hides hidden hospital OK")

# form only offers available groups
r = c.get(f"/requests/new/{hospital.pk}/")
assert b'value="O+"' in r.content and b'value="A+"' not in r.content
print("availability-driven form OK")

# hidden hospital request URL blocked
r = c.get(f"/requests/new/{hidden.pk}/")
assert r.status_code == 404
print("hidden hospital request blocked OK")

# submit request for 2 units
r = c.post(f"/requests/new/{hospital.pk}/", {"blood_group": "O+", "units_requested": 2, "urgency": "URGENT"})
assert r.status_code == 302, r.content[:300]
req = BloodRequest.objects.get(patient=patient)
assert req.status == "PENDING"
print("request submitted PENDING")

# unavailable group rejected server-side
r = c.post(f"/requests/new/{hospital.pk}/", {"blood_group": "AB-", "units_requested": 1, "urgency": "ROUTINE"})
assert r.status_code == 200  # re-render with error, no create
assert BloodRequest.objects.filter(patient=patient).count() == 1
print("unavailable group rejected OK")

# staff accepts -> FEFO: soonest expiry two bags reserved (b_soon, b_mid)
c.force_login(staff)
r = c.post(f"/requests/action/{req.pk}/", {"action": "accept"})
assert r.status_code == 302
req.refresh_from_db(); b_soon.refresh_from_db(); b_mid.refresh_from_db(); b_late.refresh_from_db()
assert req.status == "ACCEPTED"
assert b_soon.status == "RESERVED" and b_mid.status == "RESERVED" and b_late.status == "AVAILABLE"
assert AuditLog.objects.filter(action="REQUEST_ACCEPTED", entity_id=str(req.pk)).exists()
print("accept FEFO reserve OK")

# fulfil -> issued
r = c.post(f"/requests/action/{req.pk}/", {"action": "fulfil"})
req.refresh_from_db(); b_soon.refresh_from_db(); b_mid.refresh_from_db()
assert req.status == "FULFILLED" and b_soon.status == "ISSUED" and b_mid.status == "ISSUED"
assert AuditLog.objects.filter(action="BAG_ISSUED", entity_id=str(b_soon.pk)).exists()
print("fulfil issue OK")

# double fulfil blocked
try:
    services.fulfil_request(staff, req)
    raise SystemExit("double fulfil should have raised")
except ValueError:
    print("double fulfil blocked OK")

# insufficient stock accept
r2 = BloodRequest.objects.create(patient=patient, hospital=hospital, blood_group="O+", units_requested=5, urgency="EMERGENCY")
try:
    services.accept_request(staff, r2)
    raise SystemExit("should have raised InsufficientStock")
except services.InsufficientStock as exc:
    assert exc.available == 1
    print("insufficient stock raises OK")

# staff of other hospital cannot act on this request
other_staff, _ = User.objects.get_or_create(username="verify_staff2", defaults={"role": Role.HOSPITAL_STAFF})
other_staff.role = Role.HOSPITAL_STAFF
other_staff.save()
from hospitals.models import StaffProfile
StaffProfile.objects.get_or_create(user=other_staff, defaults={"hospital": hidden})
c.force_login(other_staff)
r = c.post(f"/requests/action/{r2.pk}/", {"action": "accept"})
assert r.status_code == 404
print("cross-hospital request action blocked OK")

print("STEP 6 VERIFIED")
