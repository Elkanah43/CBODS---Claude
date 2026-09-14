"""Run `manage.py runserver` with the SMTP env vars loaded from .smtp_creds.

Lets the live app send through the configured relay (e.g. Brevo) exactly as
it would with the same variables exported in the shell:

    python scripts\\run_with_brevo.py [runserver-args...]

Extra args (e.g. `0.0.0.0:8000`) are passed through to runserver.
"""
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent


def load_creds():
    creds = {}
    for raw in (SCRIPTS_DIR / ".smtp_creds").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        creds[key.strip().lower()] = value.strip()
    return creds


def main():
    creds = load_creds()
    os.environ.setdefault("EMAIL_HOST", creds.get("host", ""))
    os.environ.setdefault("EMAIL_PORT", creds.get("port", "25"))
    os.environ.setdefault("EMAIL_HOST_USER", creds.get("user", ""))
    os.environ.setdefault("EMAIL_HOST_PASSWORD", creds.get("password", ""))
    os.environ.setdefault(
        "EMAIL_USE_TLS", "1" if creds.get("tls") in ("1", "true", "yes") else "0"
    )
    os.environ.setdefault(
        "EMAIL_USE_SSL", "1" if creds.get("ssl") in ("1", "true", "yes") else "0"
    )
    os.environ.setdefault("DEFAULT_FROM_EMAIL", creds.get("from", ""))
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