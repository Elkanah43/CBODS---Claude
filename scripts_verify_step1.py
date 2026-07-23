import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings
from django.test import Client

settings.ALLOWED_HOSTS.append("testserver")

from accounts.models import User

c = Client()

r = c.get("/accounts/login/")
assert r.status_code == 200, r.status_code
print("login page OK")

r = c.get("/accounts/register/")
assert r.status_code == 200, r.status_code
print("register page OK")

User.objects.filter(username="verify_donor").delete()
r = c.post(
    "/accounts/register/",
    {
        "username": "verify_donor",
        "email": "vd@example.com",
        "phone": "0700000001",
        "role": "DONOR",
        "password1": "Str0ngPass!234",
        "password2": "Str0ngPass!234",
    },
)
assert r.status_code == 302 and r.url == "/accounts/dashboard/", (r.status_code, getattr(r, "url", None))
u = User.objects.get(username="verify_donor")
assert u.role == "DONOR"
print("register POST OK, role stored:", u.role)

r = c.get("/accounts/dashboard/")
assert r.status_code == 200
print("dashboard (logged in) OK")

r = c.post("/accounts/logout/")
assert r.status_code == 302
r = c.get("/accounts/dashboard/")
assert r.status_code == 302 and r.url.startswith("/accounts/login/")
print("logout + login-required redirect OK")

r = c.post("/accounts/login/", {"username": "verify_donor", "password": "Str0ngPass!234"})
assert r.status_code == 302 and r.url == "/accounts/dashboard/"
print("login POST OK")

r = c.get("/")
assert r.status_code == 302
print("root redirect OK")

print("STEP 1 VERIFIED")
