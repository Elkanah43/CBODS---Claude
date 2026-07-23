import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

from accounts.models import Role, User
from audit.models import AuditLog
from hospitals.models import Hospital, StaffProfile

settings.ALLOWED_HOSTS.append("testserver")

Hospital.objects.filter(name__startswith="Verify ").delete()
h1 = Hospital.objects.create(name="Verify General", city="Nairobi", address="1 Main St", phone="0711", services_offered="Blood bank")
h2 = Hospital.objects.create(name="Verify Hidden", city="Mombasa", address="2 Side St", phone="0722", is_hidden=True)

admin = User.objects.get(username="admin")
anon_visible = Hospital.objects.visible_to(User.objects.get(username="verify_donor"))
assert h1 in anon_visible and h2 not in anon_visible
assert h2 in Hospital.objects.visible_to(admin)
print("visibility gate OK")

staff_user, _ = User.objects.get_or_create(username="verify_staff", defaults={"role": Role.HOSPITAL_STAFF})
staff_user.role = Role.HOSPITAL_STAFF
staff_user.set_password("Str0ngPass!234")
staff_user.save()
sp, _ = StaffProfile.objects.get_or_create(user=staff_user, defaults={"hospital": h1})
assert sp.hospital == h1
print("StaffProfile OK")

# Admin CRUD via admin site: toggle hide, check audit row
c = Client()
c.force_login(admin)
r = c.get(f"/admin/hospitals/hospital/{h1.pk}/change/")
assert r.status_code == 200
r = c.post(
    f"/admin/hospitals/hospital/{h1.pk}/change/",
    {
        "name": h1.name, "city": h1.city, "address": h1.address, "phone": h1.phone,
        "services_offered": h1.services_offered, "organ_requirements": "",
        "is_hidden": "on",
    },
)
assert r.status_code == 302, r.status_code
h1.refresh_from_db()
assert h1.is_hidden
assert AuditLog.objects.filter(action="HOSPITAL_HIDDEN", entity_id=str(h1.pk)).exists()
print("admin hide + audit row OK")

# unhide again for later steps
r = c.post(
    f"/admin/hospitals/hospital/{h1.pk}/change/",
    {
        "name": h1.name, "city": h1.city, "address": h1.address, "phone": h1.phone,
        "services_offered": h1.services_offered, "organ_requirements": "",
    },
)
h1.refresh_from_db()
assert not h1.is_hidden
assert AuditLog.objects.filter(action="HOSPITAL_UNHIDDEN", entity_id=str(h1.pk)).exists()
print("admin unhide + audit row OK")

print("STEP 2 VERIFIED")
