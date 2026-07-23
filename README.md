# CBODS — Centralised Blood & Organ Donation System

Django 5 MVP for a final-year project: verified blood donors, hospital blood-bag
inventory, patient blood requests, organ donation requests, and admin oversight.

## Run it

```
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py seed_demo
venv\Scripts\python.exe manage.py runserver
```

Open http://localhost:8000.

## Demo accounts (password `demo12345`)

| Username | Role |
|---|---|
| `demo_admin` | Admin (system dashboard, approvals, audit log) |
| `demo_staff1` | Staff at Demo Accra Central Hospital |
| `demo_staff2` | Staff at Demo Tema Community Hospital |
| `demo_donor1` … `demo_donor25` | Donors (mixed statuses) |
| `demo_patient1` … `demo_patient3` | Patients |

There is also a Django superuser `admin` / `admin12345` for `/admin/`.

## Daily maintenance command

```
venv\Scripts\python.exe manage.py expire_bags
```

Marks past-expiry bags EXPIRED (audited) and triggers low-stock notifications.

## Tests

```
venv\Scripts\python.exe manage.py test
```

26 tests: eligibility boundaries, full compatibility tree, deny-with-alternatives,
FEFO reserve, double-issue race safety, availability-driven request form, and
privacy partitions.

## Architecture notes

- Apps: `accounts`, `hospitals`, `donors`, `inventory`, `requests_app` (blood
  requests; named to avoid clashing with the well-known `requests` package),
  `organs`, `notifications`, `audit`.
- Stock is always computed from AVAILABLE `BloodBag` rows — never stored.
- Eligibility: stage 1 (age 18–60, weight ≥ 50 kg, ≥ 90 days since last donation,
  derived from `Donation` rows) then stage 2 (hemoglobin ≥ 12.5, BP 90–180/60–100).
  Thresholds live in `cbods/settings.py`.
- Blood compatibility is a data dict in `requests_app/compatibility.py`,
  enforced in service functions, not just forms.
- Reserve/issue run inside `transaction.atomic()` with `select_for_update()`
  status re-checks so a bag can never be issued twice.
- Every mandated action writes an `AuditLog` row via `audit/services.log_action`.
- Email uses the console backend — notification emails print to the runserver
  terminal.
- `scripts_verify_step*.py` / `scripts_verify_e2e.py` are the per-step manual
  verification scripts used during the build; safe to delete.
