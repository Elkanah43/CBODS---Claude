"""Send live test emails through any SMTP relay and confirm it accepts them.

Provider-agnostic: works with Brevo, Gmail (app password), SendGrid, Mailgun,
or any other SMTP relay. The settings it applies are exactly what
cbods/settings.py reads from the environment, so a green run here means the
app's own EMAIL_* env vars will work unchanged.

Credentials are read from (never committed — scripts/.*_creds is gitignored):
  * env vars first: EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD, EMAIL_USE_TLS / EMAIL_USE_SSL, DEFAULT_FROM_EMAIL, or
  * a file scripts/.smtp_creds with key=value lines (blank lines and lines
    starting with # are ignored):

        host=smtp-relay.brevo.com
        port=587
        user=your-smtp-login@smtp-brevo.com
        password=xsmtpsib-xxxxxxxxxxxxxxxxxxxxxxxx
        tls=1
        from=CBODS <you@example.com>

`from` may include a display name ("Name <addr>"); the bare address is used
for the actual recipient, the display name only for the From header.

Credentials are optional — an unauthenticated relay (like the local
`smtp_debugserver` sink) needs only `host`.

The script sends a plain message and a real password-reset email, prints the
subjects, and tells you what to search for in the inbox. Django's
PasswordResetForm swallows send failures (it only logs them), so the script
captures the django.request log to fail honestly if the reset email was not
accepted.

Usage:
    python scripts\\verify_live_smtp.py [recipient@example.com]
The recipient defaults to the bare address of DEFAULT_FROM_EMAIL.
"""
import logging
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")

CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".smtp_creds")

_BARE_ADDR = re.compile(r"<([^<>]+)>")


def _env(key, default=""):
    return os.environ.get(key, default).strip()


def load_credentials():
    """Return a dict of settings from env vars, falling back to .smtp_creds."""
    creds = {}
    if os.path.exists(CREDS_FILE):
        with open(CREDS_FILE, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                creds[key.strip().lower()] = value.strip()

    def pick(env_name, file_key, default=""):
        value = _env(env_name)
        if not value and file_key in creds:
            value = creds[file_key]
        return value or default

    return {
        "host": pick("EMAIL_HOST", "host"),
        "port": pick("EMAIL_PORT", "port", "25"),
        "user": pick("EMAIL_HOST_USER", "user"),
        "password": pick("EMAIL_HOST_PASSWORD", "password"),
        "tls": pick("EMAIL_USE_TLS", "tls", "0").lower() in ("1", "true", "yes"),
        "ssl": pick("EMAIL_USE_SSL", "ssl", "0").lower() in ("1", "true", "yes"),
        "from": pick("DEFAULT_FROM_EMAIL", "from"),
    }


def bare_address(value):
    """Strip a display name: 'CBODS <a@b.c>' -> 'a@b.c'."""
    match = _BARE_ADDR.search(value)
    return match.group(1).strip() if match else value.strip()


def configure_smtp(settings, creds):
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = creds["host"]
    settings.EMAIL_PORT = int(creds["port"])
    settings.EMAIL_HOST_USER = creds["user"]
    settings.EMAIL_HOST_PASSWORD = creds["password"]
    settings.EMAIL_USE_TLS = creds["tls"]
    settings.EMAIL_USE_SSL = creds["ssl"]
    settings.EMAIL_TIMEOUT = 30
    settings.DEFAULT_FROM_EMAIL = creds["from"] or creds["user"] or "noreply@cbods.local"


def main():
    creds = load_credentials()
    if not creds["host"]:
        sys.exit(
            "No SMTP relay configured. Either set EMAIL_HOST (+ credentials)\n"
            "in the environment, or create scripts/.smtp_creds with key=value\n"
            "lines (host, port, user, password, tls, from) — see the docstring."
        )
    if bool(creds["user"]) != bool(creds["password"]):
        sys.exit("Set both EMAIL_HOST_USER and EMAIL_HOST_PASSWORD, or neither "
                 "(an unauthenticated relay — e.g. the local sink — needs no "
                 "credentials).")

    import django

    django.setup()

    from django.conf import settings

    configure_smtp(settings, creds)

    # The display name is only for the From header; the reset flow and the
    # recipient list need the bare address (Django's email field validates it).
    recipient = sys.argv[1] if len(sys.argv) > 1 else bare_address(
        creds["from"] or creds["user"]
    )
    code = f"CBODS-{int(time.time())}"
    subject = f"[CBODS] live SMTP check {code}"
    print(f"Relay : {creds['host']}:{creds['port']} "
          f"(TLS={creds['tls']} SSL={creds['ssl']})")
    print(f"Auth  : {creds['user'] or '(no auth)'}")
    print(f"From  : {settings.DEFAULT_FROM_EMAIL}")
    print(f"To    : {recipient}")

    # --- 1. plain message -----------------------------------------------
    from django.core.mail import send_mail

    sent = send_mail(
        subject=subject,
        message=("If you see this in your inbox, live SMTP delivery works.\n"
                 f"Check code: {code}\n"),
        from_email=None,  # DEFAULT_FROM_EMAIL
        recipient_list=[recipient],
    )
    if sent != 1:
        sys.exit(f"FAIL: the relay did not accept the message (sent={sent}).")
    print(f"[1/2] plain message accepted: subject: {subject}")

    # --- 2. real password-reset email through the same backend ----------
    # Django's PasswordResetForm swallows send failures (it only logs them and
    # still returns 302), so capture the log to detect a failed send honestly.
    from django.test import Client

    from accounts.models import Role, User

    username = "smtp_verify_user"
    User.objects.filter(username=username).delete()
    User.objects.create_user(
        username=username, email=recipient, password="Verify!23456789",
        role=Role.PATIENT,
    )
    failures = []
    log_handler = logging.Handler()
    log_handler.emit = failures.append
    logger = logging.getLogger("django.request")
    logger.addHandler(log_handler)
    try:
        client = Client()
        response = client.post(
            "/accounts/password-reset/", {"email": recipient},
            HTTP_HOST="localhost",   # ALLOWED_HOSTS has no 'testserver'
        )
        if response.status_code != 302:
            sys.exit(f"FAIL: reset request returned {response.status_code} "
                     f"(is that address already a CBODS account?).")
        if any("Failed to send password reset email" in rec.getMessage()
               for rec in failures):
            sys.exit("FAIL: the relay rejected the password-reset email "
                     "(see the send error above).")
        print("[2/2] password-reset email accepted: subject "
              "'Reset your CBODS password'")
    finally:
        logger.removeHandler(log_handler)
        User.objects.filter(username=username).delete()

    print("\nThe relay accepted both messages over SMTP.")
    print("Confirm inbox delivery: open the inbox of", recipient, "and search")
    print("  subject:", subject)
    print("Both emails should arrive within a minute. If they do not, check")
    print("the Spam folder first, then sender verification on the relay side.")


if __name__ == "__main__":
    main()