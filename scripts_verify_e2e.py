"""Full end-to-end demo flow on the seeded database, per the spec's Done-when list."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.models import Role, User
from audit.models import AuditLog
from donors.models import Donor
from inventory.models import BloodBag, Donation
from notifications.models import Notification
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest

settings.ALLOWED_HOSTS.append("testserver")

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcff9fa10e0002d40197ec1f83660000000049454e44ae426082"
)

c = Client()
User.objects.filter(username__in=["e2e_donor", "e2e_patient"]).delete()

# 1. donor registers with ID
r = c.post("/accounts/register/", {
    "username": "e2e_donor", "email": "e2e_d@example.com", "phone": "0799",
    "role": "DONOR", "password1": "Str0ngPass!234", "password2": "Str0ngPass!234",
})
assert r.status_code == 302
r = c.post("/donors/profile/", {
    "full_name": "E2E Donor", "date_of_birth": "1992-03-03", "sex": "F",
    "blood_group": "B+", "weight_kg": "68.0", "city": "Nairobi",
    "contact_phone": "0799-1", "medical_history": "",
    "id_document": SimpleUploadedFile("e2e.png", PNG, content_type="image/png"),
})
assert r.status_code == 302
donor = Donor.objects.get(user__username="e2e_donor")
assert donor.registration_status == "PENDING"
print("1. donor registered with ID, PENDING")

# 2. admin approves (sees ID on the approval page)
admin = User.objects.get(username="demo_admin")
c.force_login(admin)
r = c.get(f"/donors/approvals/{donor.pk}/")
assert donor.id_document.url.encode() in r.content
r = c.post(f"/donors/approvals/{donor.pk}/", {"action": "approve"})
donor.refresh_from_db()
assert donor.registration_status == "APPROVED"
assert Notification.objects.filter(user=donor.user, subject__icontains="approved").exists()
print("2. admin approved after ID preview; donor notified")

# 3. staff screening passes
staff = User.objects.get(username="demo_staff1")
hospital = staff.staff_profile.hospital
c.force_login(staff)
r = c.post(f"/donors/screening/{donor.pk}/", {"hemoglobin_g_dl": "13.8", "systolic_bp": "118", "diastolic_bp": "76"})
assert r.status_code == 302
assert donor.screenings.first().outcome == "ELIGIBLE"
print("3. screening ELIGIBLE")

# 4. donation creates AVAILABLE bag
r = c.post("/inventory/donate/", {"donor": donor.pk, "volume_ml": 450})
assert r.status_code == 302
bag = BloodBag.objects.get(donation__donor=donor)
assert bag.status == "AVAILABLE" and bag.hospital == hospital and bag.blood_group == "B+"
print("4. donation recorded; bag AVAILABLE at", hospital.name)

# 5. patient requests an available group
c.post("/accounts/logout/")
r = c.post("/accounts/register/", {
    "username": "e2e_patient", "email": "e2e_p@example.com", "phone": "0788",
    "role": "PATIENT", "password1": "Str0ngPass!234", "password2": "Str0ngPass!234",
})
assert r.status_code == 302
patient = User.objects.get(username="e2e_patient")
r = c.get(f"/requests/new/{hospital.pk}/")
assert b'value="B+"' in r.content
r = c.post(f"/requests/new/{hospital.pk}/", {"blood_group": "B+", "units_requested": 1, "urgency": "URGENT"})
assert r.status_code == 302
req = BloodRequest.objects.get(patient=patient)
print("5. patient requested available group B+")

# 6. staff reserves (FEFO) and issues
c.force_login(staff)
r = c.post(f"/requests/action/{req.pk}/", {"action": "accept"})
req.refresh_from_db()
assert req.status == "ACCEPTED"
r = c.post(f"/requests/action/{req.pk}/", {"action": "fulfil"})
req.refresh_from_db()
assert req.status == "FULFILLED"
assert Notification.objects.filter(user=patient, subject__icontains="fulfilled").exists()
print("6. staff reserved (FEFO) and issued; patient notified")

# 7. emergency broadcast when stock short
Notification.objects.filter(subject__startswith="URGENT").delete()
avail_ab_neg = BloodBag.objects.filter(hospital=hospital, blood_group="AB-", status="AVAILABLE").count()
emerg = BloodRequest.objects.create(
    patient=patient, hospital=hospital, blood_group="AB-",
    units_requested=avail_ab_neg + 10, urgency="EMERGENCY",
)
r = c.post(f"/requests/action/{emerg.pk}/", {"action": "accept"}, follow=True)
assert b"Emergency broadcast sent" in r.content
assert Notification.objects.filter(subject__startswith="URGENT").exists()
assert b"Compatible donor suggestions" in r.content
print("7. emergency broadcast fired; ranked suggestions shown")

# 8. organ request PENDING -> APPROVED live on donor dashboard
c.force_login(donor.user)
r = c.post("/organs/new/", {"organ_type": "CORNEA", "hospital": hospital.pk})
organ = OrganDonationRequest.objects.get(donor=donor)
assert organ.status == "PENDING"
c.force_login(staff)
c.post(f"/organs/review/{organ.pk}/", {"status": "APPROVED"})
organ.refresh_from_db()
assert organ.status == "APPROVED"
c.force_login(donor.user)
r = c.get("/accounts/dashboard/")
assert b"Cornea" in r.content and b"Approved" in r.content
print("8. organ request Pending -> Approved, live on donor dashboard")

# 9. admin dashboard + audit reflect everything
c.force_login(admin)
r = c.get("/audit/dashboard/")
assert r.status_code == 200
r = c.get("/audit/log/")
for action in [b"DONOR_APPROVED", b"BAG_CREATED", b"BAG_RESERVED", b"BAG_ISSUED",
               b"REQUEST_ACCEPTED", b"REQUEST_FULFILLED", b"ORGAN_REQUEST_APPROVED"]:
    assert AuditLog.objects.filter(action=action.decode()).exists(), action
assert r.status_code == 200
print("9. admin dashboard + audit log reflect the full flow")

print("END-TO-END DEMO VERIFIED")
