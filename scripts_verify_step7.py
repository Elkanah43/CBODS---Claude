import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import User
from donors.models import Donor
from requests_app.compatibility import COMPATIBLE_DONORS, check_donor_for_recipient, is_compatible, suggest_donors

settings.ALLOWED_HOSTS.append("testserver")

# full decision-tree spot check
expected = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": {"O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+"},
}
for recipient, donors_set in expected.items():
    assert set(COMPATIBLE_DONORS[recipient]) == donors_set, recipient
    for g in ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]:
        assert is_compatible(recipient, g) == (g in donors_set)
print("compatibility tree all 8 groups OK")

staff = User.objects.get(username="verify_staff")
hospital = staff.staff_profile.hospital

# deny-with-alternatives at service level
donor_opos = Donor.objects.get(user__username="verify_donor")  # O+
ok, alt = check_donor_for_recipient(hospital, "O-", donor_opos)
assert not ok and alt is not None
print("service-level deny with alternatives OK")

ok, alt = check_donor_for_recipient(hospital, "AB+", donor_opos)
assert ok and alt is None
print("service-level compatible OK")

# ranking: same city first
suggestions = suggest_donors(hospital, "AB+", "EMERGENCY")
cities = [d.city.lower() == hospital.city.lower() for d in suggestions]
assert cities == sorted(cities, reverse=True), cities
print("ranking same-city-first OK")

c = Client()
c.force_login(staff)
r = c.get("/donors/search/")
assert r.status_code == 200 and b"Verify Donor" in r.content and b"0700000001" in r.content
print("donor search with contact for staff OK")

r = c.get("/donors/search/?blood_group=AB-")
assert b"Verify Donor" not in r.content
r = c.get("/donors/search/?city=nairobi")
assert b"Verify Donor" in r.content
print("search filters OK")

# compatibility page deny path
r = c.post("/requests/match/", {"recipient_group": "O-", "donor": donor_opos.pk, "urgency": "ROUTINE"})
assert r.status_code == 200 and b"Denied" in r.content
print("compatibility page deny + alternatives OK")

# privacy: patient and donor blocked from search
patient = User.objects.get(username="verify_patient")
c.force_login(patient)
r = c.get("/donors/search/")
assert r.status_code == 403
c.force_login(donor_opos.user)
r = c.get("/donors/search/")
assert r.status_code == 403
print("donor search role gate OK")

# admin allowed
c.force_login(User.objects.get(username="admin"))
r = c.get("/donors/search/")
assert r.status_code == 200
print("admin can search OK")

print("STEP 7 VERIFIED")
