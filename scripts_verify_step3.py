import io
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import User
from audit.models import AuditLog
from donors.models import Donor
from notifications.models import Notification

settings.ALLOWED_HOSTS.append("testserver")

# tiny valid PNG (1x1)
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcff9fa10e0002d40197ec1f83660000000049454e44ae426082"
)

c = Client()
donor_user = User.objects.get(username="verify_donor")
Donor.objects.filter(user=donor_user).delete()
c.force_login(donor_user)

r = c.get("/donors/profile/")
assert r.status_code == 200
print("donor profile form loads")

r = c.post(
    "/donors/profile/",
    {
        "full_name": "Verify Donor", "date_of_birth": "1995-05-10", "sex": "M",
        "blood_group": "O+", "weight_kg": "70.5", "city": "Nairobi",
        "contact_phone": "0700000001", "medical_history": "none",
        "id_document": SimpleUploadedFile("id.png", PNG, content_type="image/png"),
    },
)
assert r.status_code == 302, (r.status_code, r.content[:500])
d = Donor.objects.get(user=donor_user)
assert d.registration_status == "PENDING"
print("donor registration submitted, PENDING")

# privacy: donor cannot open approval queue
r = c.get("/donors/approvals/")
assert r.status_code == 403
print("role gate on approval queue OK (403 for donor)")

# admin approves
admin = User.objects.get(username="admin")
c.force_login(admin)
r = c.get("/donors/approvals/")
assert r.status_code == 200 and b"Verify Donor" in r.content
r = c.get(f"/donors/approvals/{d.pk}/")
assert r.status_code == 200 and d.id_document.url.encode() in r.content
print("approval queue + ID preview OK")

r = c.post(f"/donors/approvals/{d.pk}/", {"action": "approve"})
assert r.status_code == 302
d.refresh_from_db()
assert d.registration_status == "APPROVED"
assert AuditLog.objects.filter(action="DONOR_APPROVED", entity_id=str(d.pk)).exists()
assert Notification.objects.filter(user=donor_user, subject__icontains="approved").exists()
print("approve -> APPROVED + audit + notification OK")

# rejection path on a second donor
u2, _ = User.objects.get_or_create(username="verify_donor2", defaults={"role": "DONOR", "email": "vd2@example.com"})
u2.role = "DONOR"; u2.save()
Donor.objects.filter(user=u2).delete()
d2 = Donor.objects.create(
    user=u2, full_name="Verify Donor Two", date_of_birth="1990-01-01", sex="F",
    blood_group="A-", weight_kg=60, city="Kisumu", contact_phone="0700000002",
    id_document=SimpleUploadedFile("id2.png", PNG, content_type="image/png"),
)
r = c.post(f"/donors/approvals/{d2.pk}/", {"action": "reject", "rejection_reason": "ID unreadable"})
assert r.status_code == 302
d2.refresh_from_db()
assert d2.registration_status == "REJECTED" and d2.rejection_reason == "ID unreadable"
assert Notification.objects.filter(user=u2, subject__icontains="rejected").exists()
assert AuditLog.objects.filter(action="DONOR_REJECTED", entity_id=str(d2.pk)).exists()
print("reject -> REJECTED + reason + audit + notification OK")

print("STEP 3 VERIFIED")
