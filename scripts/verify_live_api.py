"""Verify live email delivery through Brevo's HTTPS API (not SMTP).

The HTTPS counterpart of verify_live_smtp.py, for when the network blocks or
stalls port 587 but normal HTTPS works. Sends, through the same
accounts.email.BrevoHTTPSBackend the app uses:

  1. a plain test message, and
  2. a real password-reset email for a throwaway account, the way the app
     itself sends it (Django's PasswordResetForm swallows send errors — it
     logs them and still redirects — so the send log is watched directly).

Credentials come from the environment or from scripts/.api_creds with
key=value lines (blank lines and #-comments ignored):

    BREVO_API_KEY=xkeysib-...     (the API key, NOT the SMTP key xsmtpsib-...)
    from=you@example.com          (a verified sender in Brevo)

Environment names are the settings names themselves: BREVO_API_KEY and
DEFAULT_FROM_EMAIL; the file accepts their short forms (api_key, from).
Environment wins over the file. Usage:

    python scripts\\verify_live_api.py [recipient@example.com]

Without a recipient the verified sender address is used, so sending to
yourself is the zero-argument default. Exit code 0 means Brevo's API
accepted both messages (201 with messageIds); inbox delivery is confirmed
by the human reading the inbox.
"""
import logging
import os
import re
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")

CREDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".api_creds")

_BARE_ADDR = re.compile(r"<([^<>]+)>")


def _env(key, default=""):
    return os.environ.get(key, default).strip()


def load_credentials():
    """Return a dict of settings from env vars, falling back to .api_creds."""
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
        "api_key": pick("BREVO_API_KEY", "api_key"),
        "from": pick("DEFAULT_FROM_EMAIL", "from"),
    }


def bare_address(value):
    """Strip a display name: 'CBODS <a@b.c>' -> 'a@b.c'."""
    match = _BARE_ADDR.search(value)
    return match.group(1).strip() if match else value.strip()


def masked_key(key):
    """Enough of the key to recognise which one is in use, not enough to leak."""
    if len(key) > 20:
        return f"{key[:12]}…{key[-4:]}"
    return "(set)"


def configure_api(settings, creds):
    # SMTP wins in settings.py when EMAIL_HOST is set; this script is for the
    # opposite situation, so force the HTTPS backend explicitly either way.
    settings.EMAIL_BACKEND = "accounts.email.BrevoHTTPSBackend"
    settings.BREVO_API_KEY = creds["api_key"]
    if creds["from"]:
        settings.DEFAULT_FROM_EMAIL = creds["from"]


def main():
    creds = load_credentials()
    if not creds["api_key"]:
        sys.exit(
            "No Brevo API key configured. Either set BREVO_API_KEY in the\n"
            "environment, or create scripts/.api_creds with key=value lines\n"
            "(api_key, from) — see the docstring. Use the API key\n"
            "(xkeysib-…), not the SMTP key (xsmtpsib-…)."
        )

    import django

    django.setup()

    from django.conf import settings

    configure_api(settings, creds)

    # The display name is only for the From header; the reset flow and the
    # recipient list need the bare address (Django's email field validates it).
    recipient = sys.argv[1] if len(sys.argv) > 1 else bare_address(creds["from"])
    if not recipient:
        sys.exit(
            "No recipient. Pass one: python scripts\\verify_live_api.py "
            "you@example.com — or set from=/DEFAULT_FROM_EMAIL (a verified "
            "sender) so the script can send to itself."
        )
    if not creds["from"]:
        print(
            "NOTE: no from=/DEFAULT_FROM_EMAIL given; using "
            f"{settings.DEFAULT_FROM_EMAIL}. Brevo only accepts a verified "
            "sender, so expect a refusal unless that address is verified."
        )
    code = f"CBODS-{int(time.time())}"
    subject = f"[CBODS] live Brevo API check {code}"
    print(f"API   : {settings.EMAIL_BACKEND} -> api.brevo.com/v3/smtp/email")
    print(f"Auth  : api-key {masked_key(creds['api_key'])}")
    print(f"From  : {settings.DEFAULT_FROM_EMAIL}")
    print(f"To    : {recipient}")

    # --- 1. plain message -----------------------------------------------
    from django.core.mail import send_mail

    from accounts.email import BrevoAPIError

    try:
        sent = send_mail(
            subject=subject,
            message=("If you see this in your inbox, live Brevo API delivery "
                     "works.\n"
                     f"Check code: {code}\n"),
            from_email=None,  # DEFAULT_FROM_EMAIL
            recipient_list=[recipient],
        )
    except BrevoAPIError as exc:
        sys.exit(f"FAIL: the API refused the message: {exc}")
    if sent != 1:
        sys.exit(f"FAIL: the API did not accept the message (sent={sent}).")
    print(f"[1/2] plain message accepted: subject: {subject}")

    # --- 2. real password-reset email through the same backend ----------
    # Django's PasswordResetForm.send_mail swallows send errors (it logs them
    # and still redirects), so capture the log to detect a failed send
    # honestly. The exception lands on logger 'django.contrib.auth', not
    # 'django.request' — both get the probe so any request-level error is
    # caught too.
    from django.test import Client

    from accounts.models import Role, User

    username = "api_verify_user"
    User.objects.filter(username=username).delete()
    User.objects.create_user(
        username=username, email=recipient, password="Verify!23456789",
        role=Role.PATIENT,
    )
    failures = []
    log_handler = logging.Handler()
    log_handler.emit = failures.append
    auth_logger = logging.getLogger("django.contrib.auth")
    request_logger = logging.getLogger("django.request")
    auth_logger.addHandler(log_handler)
    request_logger.addHandler(log_handler)
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
            sys.exit("FAIL: the API rejected the password-reset email "
                     "(see the send error above).")
        print("[2/2] password-reset email accepted: subject "
              "'Reset your CBODS password'")
    finally:
        auth_logger.removeHandler(log_handler)
        request_logger.removeHandler(log_handler)
        User.objects.filter(username=username).delete()

    print("\nThe API accepted both messages over HTTPS.")
    print("Confirm inbox delivery: open the inbox of", recipient, "and search")
    print("  subject:", subject)
    print("Both emails should arrive within a minute. If they do not, check")
    print("the Spam folder first, then sender verification on Brevo's side")
    print("(Settings -> Senders).")


if __name__ == "__main__":
    main()
