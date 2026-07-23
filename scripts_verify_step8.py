import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import User
from audit.models import AuditLog
from donors.models import Donor
from hospitals.models import Hospital
from notifications.models import Notification
from organs.models import OrganDonationRequest

settings.ALLOWED_HOSTS.append("testserver")

donor = Donor.objects.get(user__username="verify_donor")
staff = User.objects.get(username="verify_staff")
hospital = staff.staff_profile.hospital
OrganDonationRequest.objects.filter(donor=donor).delete()

c = Client()
c.force_login(donor.user)

# create organ request
r = c.get("/organs/new/")
assert r.status_code == 200
r = c.post("/organs/new/", {"organ_type": "KIDNEY", "hospital": hospital.pk})
assert r.status_code == 302, r.content[:300]
req = OrganDonationRequest.objects.get(donor=donor)
assert req.status == "PENDING" and req.decided_at is None
print("organ request created PENDING")

# hidden hospital not offered in form
hidden = Hospital.objects.get(name="Verify Hidden")
r = c.get("/organs/new/")
assert b"Verify Hidden" not in r.content
print("hidden hospital excluded from organ form OK")

# donor dashboard shows live status
r = c.get("/accounts/dashboard/")
assert b"Kidney" in r.content and b"Pending" in r.content
print("donor dashboard live status OK")

# staff review: REQUESTED then APPROVED
c.force_login(staff)
r = c.get("/organs/review/")
assert r.status_code == 200 and b"Kidney" in r.content
r = c.post(f"/organs/review/{req.pk}/", {"status": "REQUESTED"})
req.refresh_from_db()
assert req.status == "REQUESTED" and req.decided_at is None
assert Notification.objects.filter(user=donor.user, subject__icontains="requested").exists()
r = c.post(f"/organs/review/{req.pk}/", {"status": "APPROVED"})
req.refresh_from_db()
assert req.status == "APPROVED" and req.decided_at is not None
assert AuditLog.objects.filter(action="ORGAN_REQUEST_APPROVED", entity_id=str(req.pk)).exists()
assert Notification.objects.filter(user=donor.user, subject__icontains="approved", body__icontains="Kidney").exists()
print("staff review REQUESTED -> APPROVED + decided_at + audit + notifications OK")

# donor sees APPROVED live
c.force_login(donor.user)
r = c.get("/accounts/dashboard/")
assert b"Approved" in r.content
print("donor dashboard shows APPROVED OK")

# other-hospital staff cannot act
other_staff = User.objects.get(username="verify_staff2")
c.force_login(other_staff)
r = c.post(f"/organs/review/{req.pk}/", {"status": "REJECTED"})
assert r.status_code == 404
print("cross-hospital organ action blocked OK")

# patient cannot access review list or donor organ pages
patient = User.objects.get(username="verify_patient")
c.force_login(patient)
assert c.get("/organs/review/").status_code == 403
assert c.get("/organs/mine/").status_code == 403
print("organ role gates OK")

print("STEP 8 VERIFIED")
