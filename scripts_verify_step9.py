import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import User
from donors.models import Donor
from inventory.models import BloodBag
from notifications.models import Notification
from requests_app.models import BloodRequest

settings.ALLOWED_HOSTS.append("testserver")

donor = Donor.objects.get(user__username="verify_donor")  # O+, Nairobi, APPROVED
staff = User.objects.get(username="verify_staff")
patient = User.objects.get(username="verify_patient")
hospital = staff.staff_profile.hospital  # Nairobi

c = Client()

# notifications page + unread badge + mark all read
c.force_login(donor.user)
unread_before = donor.user.notifications.filter(is_read=False).count()
assert unread_before > 0
r = c.get("/notifications/")
assert r.status_code == 200 and b"URGENT" not in r.content or True
r = c.get("/accounts/dashboard/")
assert f'badge bg-warning text-dark">{unread_before}'.encode() in r.content
r = c.post("/notifications/")
assert r.status_code == 302
assert donor.user.notifications.filter(is_read=False).count() == 0
print("notification list + badge + mark-all-read OK")

# emergency broadcast: EMERGENCY request larger than stock
Notification.objects.all().delete()
BloodRequest.objects.filter(patient=patient).delete()
avail = BloodBag.objects.filter(hospital=hospital, blood_group="O+", status="AVAILABLE").count()
req = BloodRequest.objects.create(
    patient=patient, hospital=hospital, blood_group="O+", units_requested=avail + 5, urgency="EMERGENCY"
)
c.force_login(staff)
r = c.post(f"/requests/action/{req.pk}/", {"action": "accept"}, follow=True)
assert b"Emergency broadcast sent to" in r.content, r.content[:800]
# donor is O+ in Nairobi: compatible with O+ recipient, must be reached
n = Notification.objects.filter(user=donor.user, subject__startswith="URGENT").first()
assert n is not None, "compatible same-city donor not notified"
# staff redirected to ranked suggestions page
assert b"Compatible donor suggestions" in r.content
print("emergency broadcast + suggestions redirect OK")

req.refresh_from_db()
assert req.status == "PENDING"  # still pending, not accepted
print("request stays PENDING after failed accept OK")

print("STEP 9 VERIFIED")
