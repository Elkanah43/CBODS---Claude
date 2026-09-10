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

## Configuration (environment variables)

All optional — the app runs with development defaults if none are set.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure dev key | Must be set to a fresh random value anywhere the app is reachable by others. Never commit it. |
| `DJANGO_DEBUG` | `1` | Set to `0` outside local development. |
| `DJANGO_ALLOWED_HOSTS` | *(empty)* | Comma-separated extra hosts, e.g. your LAN IP when demoing to partners. |
| `EMAIL_HOST` | *(unset → console backend)* | SMTP server to deliver email through; setting it switches the app to the real SMTP backend. |
| `EMAIL_PORT` | `25` | SMTP port (`587` with STARTTLS for Gmail, `465` for implicit TLS). |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | *(empty)* | SMTP credentials; only used when both are set. |
| `EMAIL_USE_TLS` / `EMAIL_USE_SSL` | `0` | Enable STARTTLS or implicit TLS. |
| `EMAIL_TIMEOUT` | `15` | Seconds a send waits on the network before failing. |
| `DEFAULT_FROM_EMAIL` | `noreply@cbods.local` | From address on every email; falls back to `EMAIL_HOST_USER` when a relay is configured. |

Showing it to partners on the same Wi-Fi:

```bash
DJANGO_ALLOWED_HOSTS=192.168.1.50 python manage.py runserver 0.0.0.0:8000
```

Note your machine's LAN IP can change between sessions (`ipconfig` on Windows).

Generate a new secret key at any time with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Email (SMTP)

Email defaults to Django's console backend: nothing is sent, messages print to
the runserver terminal, and each password-reset link is logged behind the
`CBODS-RESET-LINK` marker so it can be searched out of a busy log.

Setting `EMAIL_HOST` switches every message (notifications and password
resets) to Django's real SMTP backend. Try it locally with the built-in debug
sink, in two terminals:

```
set EMAIL_HOST=localhost
python manage.py smtp_debugserver      # terminal 1: accepts and prints mail
python manage.py runserver             # terminal 2: the app
```

Request a password reset in the app and the email — link included — appears in
full in the sink's output. The sink accepts anything and delivers nothing, so
it is safe for demos. It is a small standard-library SMTP server, so it works
anywhere with no extra dependencies.

### Recommended relay: Brevo (free tier)

The least-friction way to get real inbox delivery — no 2-Step Verification, no
per-user app passwords, no domain, no credit card:

1. Sign up at https://www.brevo.com (email + password is enough).
2. Settings → SMTP & API: note the **SMTP login** and generate an **SMTP key**
   (use the SMTP key, not an API key).
3. Verify a sender address once — Settings → Senders: your signup email works.
   That address is your `DEFAULT_FROM_EMAIL`.
4. Configure the app:

```
set EMAIL_HOST=smtp-relay.brevo.com
set EMAIL_PORT=587
set EMAIL_HOST_USER=your-smtp-login@smtp-brevo.com
set EMAIL_HOST_PASSWORD=xsmtpsib-xxxxxxxxxxxxxxxxxxxxxxxx
set EMAIL_USE_TLS=1
```

`DEFAULT_FROM_EMAIL` defaults to the SMTP login, so it only needs setting if
you send from a different verified address. Free tier: 300 emails/day,
forever.

Gmail works too, but needs 2-Step Verification plus a 16-character app
password (https://myaccount.google.com/apppasswords), not the account
password:

```
set EMAIL_HOST=smtp.gmail.com
set EMAIL_PORT=587
set EMAIL_HOST_USER=you@gmail.com
set EMAIL_HOST_PASSWORD=xxxxxxxxxxxxxxxx
set EMAIL_USE_TLS=1
set DEFAULT_FROM_EMAIL=you@gmail.com
```

Other relays may use implicit TLS on port 465 (`EMAIL_USE_SSL=1` instead of
`EMAIL_USE_TLS`). Password resets fail loudly rather than vanish silently;
`EMAIL_TIMEOUT` (default 15 s) bounds how long a send waits on the network.

Two verification scripts live in `scripts/` (gitignored):

- `scripts/verify_smtp.py` — one-shot check against the local sink: starts
  it, sends a plain message and a password reset through the real SMTP
  backend, follows the reset link, prints the delivered emails:

```
python scripts\verify_smtp.py
```

- `scripts/verify_live_smtp.py` — live send through any relay. Reads
  `EMAIL_HOST`/`EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` etc. from the
  environment or from `scripts/.smtp_creds` (key=value lines: `host`, `port`,
  `user`, `password`, `tls`, `from`), sends a plain message and a real
  password-reset email, and prints the subjects to search for in the inbox:

```
python scripts\verify_live_smtp.py you@example.com
```

For day-to-day operations — free-tier limits, SMTP-key rotation (keys expire
after 90 days of inactivity), and what to check when a reset email does not
arrive — see [docs/EMAIL_OPS.md](docs/EMAIL_OPS.md).

## Privacy of ID documents

Uploaded government IDs are **not** served as ordinary media files. `MEDIA_ROOT`
has no URL route; the scans are streamed only by `donors.views.id_document`,
which is restricted to ADMIN. Uploads are limited to JPG/PNG/PDF under 5 MB.

## Donor self-service

Donors register themselves with a government ID. Rejected applications can be
corrected and resubmitted for review; approved donors can edit their own
profile details (blood group, contact info, availability, and so on).

## Appointments

From **Where to donate**, an approved donor can book a donation appointment at
any listed hospital. Hospitals short on the donor's blood group get the
prominent "Book now — urgent need" button, so donors land where blood is
scarcest. Hospital staff confirm or decline the request from an inbox; the
donor is notified either way and can cancel a pending booking. Every booking,
confirmation and cancellation is audited.

## Sessions & security

Sessions idle out after 15 minutes: a countdown warning appears before
auto-logout, and any activity rolls the deadline forward. Password resets use
an emailed one-time link valid for 24 hours.

## Daily maintenance command

```
venv\Scripts\python.exe manage.py expire_bags
```

Marks past-expiry bags EXPIRED (audited) and triggers low-stock notifications.

## Tests

```
venv\Scripts\python.exe manage.py test
```

123 tests: eligibility boundaries, full compatibility tree, deny-with-alternatives,
FEFO reserve, double-issue race safety, per-request reservation isolation,
availability-driven request form, ID-document privacy, upload validation, privacy
partitions, the password-reset flow and reset-link logging, password-rule
feedback, the 15-minute idle session timeout, donor profile editing, appointment
booking with urgent-need ranking, and a render test that loads every page for
every role that can reach it.

`cbods/tests_e2e.py` drives the entire demo story over HTTP in one test —
donor registers with ID, admin approves, screening passes, donation creates a
bag, patient requests it, staff reserve and issue, emergency broadcast fires,
organ request moves Pending to Approved, and the audit log records every step.
Run just that one with:

```bash
python manage.py test cbods
```

## Data model

See [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) for the full entity relationship
diagram (all eleven models, their fields, and the design reasoning).

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
- Email defaults to the console backend — notification emails print to the
  runserver terminal. Setting `EMAIL_HOST` switches everything to real SMTP
  (see [Email (SMTP)](#email-smtp)).
