import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import User
from audit.models import AuditLog

settings.ALLOWED_HOSTS.append("testserver")

c = Client()
admin = User.objects.get(username="admin")
c.force_login(admin)

r = c.get("/audit/dashboard/")
assert r.status_code == 200
assert b"charts-data" in r.content and b"chart.js" in r.content.lower()
assert b"Donors by status" in r.content
print("admin dashboard + Chart.js OK")

r = c.get("/audit/log/")
assert r.status_code == 200 and b"BAG_CREATED" in r.content or b"DONOR_APPROVED" in r.content
print("audit log page OK")

r = c.get("/audit/log/?action=DONOR")
assert r.status_code == 200 and b"DONOR_APPROVED" in r.content
print("audit filter OK")

# mandated audit actions all present from earlier flows
for action in ["DONOR_APPROVED", "DONOR_REJECTED", "HOSPITAL_HIDDEN", "HOSPITAL_UNHIDDEN",
               "BAG_CREATED", "BAG_RESERVED", "BAG_ISSUED", "BAG_EXPIRED",
               "REQUEST_ACCEPTED", "REQUEST_FULFILLED", "ORGAN_REQUEST_APPROVED"]:
    assert AuditLog.objects.filter(action=action).exists(), f"missing audit action {action}"
print("all mandated audit actions wired OK")

# role gates
staff = User.objects.get(username="verify_staff")
c.force_login(staff)
assert c.get("/audit/dashboard/").status_code == 403
assert c.get("/audit/log/").status_code == 403
print("admin-only gates OK")

print("STEP 10 VERIFIED")
