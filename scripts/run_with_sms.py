"""Run `manage.py runserver` with the SMS env vars loaded from .sms_creds.

The phone-reset flow reads SMS_PROVIDER, AT_USERNAME, AT_API_KEY, AT_SANDBOX
and SMS_SENDER_ID from the environment; this loads them from
scripts/.sms_creds so the provider does not depend on which terminal the
server happens to be started from (the cause of "the code never arrived" —
the server had defaulted to console mode):

    python scripts\\run_with_sms.py [runserver-args...]

Extra args (e.g. `0.0.0.0:8000`) are passed through to runserver. Pair it
with scripts/run_with_brevo.py (email), or set both files' variables in the
shell and start runserver directly when you need both channels.
"""
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent

SMS_KEYS = ("SMS_PROVIDER", "AT_USERNAME", "AT_API_KEY", "AT_SANDBOX", "SMS_SENDER_ID", "SASUSYNC_API_KEY", "SASUSYNC_API_BASE")


def load_creds():
    creds = {}
    for raw in (SCRIPTS_DIR / ".sms_creds").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        creds[key.strip()] = value.strip()
    return creds


def main():
    creds = load_creds()
    missing = [key for key in ("SMS_PROVIDER", "AT_API_KEY") if not creds.get(key)]
    if missing:
        print(
            f"scripts/.sms_creds is missing {', '.join(missing)}. "
            "Fill it in (see the comments in that file) or delete SMS_PROVIDER from it to fall back to console mode.",
            file=sys.stderr,
        )
        sys.exit(2)
    for key in SMS_KEYS:
        if creds.get(key):
            os.environ.setdefault(key, creds[key])
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")

    sys.path.insert(0, str(PROJECT_ROOT))
    import django

    django.setup()

    from django.core.management import execute_from_command_line

    args = ["manage.py", "runserver", "--noreload"]
    if len(sys.argv) > 1:
        args = ["manage.py", "runserver", *sys.argv[1:], "--noreload"]
    execute_from_command_line(args)


if __name__ == "__main__":
    main()
