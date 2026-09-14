"""Live SMS verification for the phone-based password reset.

The defence-day equivalent of verify_live_smtp.py: one command that proves
the configured SMS provider accepts a real send, before anyone depends on
it in front of an audience.

Usage:
    python scripts/verify_live_sms.py --to 024 000 0001

Reads the same environment the app reads (SMS_PROVIDER, SASUSYNC_API_KEY,
AT_USERNAME/AT_API_KEY, SMS_SENDER_ID). If scripts/.sms_creds exists, its
values fill in any variables the shell did not set — real environment
variables always win. With no provider configured anywhere it uses the
console provider — nothing leaves the machine, the message is printed with
the CBODS-RESET-SMS marker, and the script exits 0. That mode checks the
wiring without spending credit or needing an account.

Exit codes: 0 sent (or logged, console mode), 1 provider refused/unreachable,
2 bad usage.
"""
import argparse
import sys
from pathlib import Path

# Running a file inside scripts/ puts scripts/ on sys.path, not the project
# root; add the root so cbods.settings resolves.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import django
import os


def _load_sms_creds():
    """Optional scripts/.sms_creds fallback; real environment variables win."""
    path = Path(__file__).resolve().parent / ".sms_creds"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and value.strip():
            os.environ.setdefault(key.strip(), value.strip())


_load_sms_creds()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")
django.setup()

from django.conf import settings  # noqa: E402

from accounts.sms import SmsSendError, normalize_ghana_phone, send_sms  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Send one live test SMS through the configured provider.")
    parser.add_argument("--to", required=True, help="Ghanaian number in any common format, e.g. 024-000-0001")
    args = parser.parse_args()

    try:
        phone = normalize_ghana_phone(args.to)
    except ValueError as exc:
        print(f"Cannot use that number: {exc}", file=sys.stderr)
        return 2

    provider = getattr(settings, "SMS_PROVIDER", "console")
    text = "CBODS test message. If you can read this, SMS password resets are working."
    try:
        used = send_sms(phone, text)
    except SmsSendError as exc:
        print(f"FAILED via {provider}: {exc}", file=sys.stderr)
        print("Check the cbods.sms log lines above for the provider's own detail.", file=sys.stderr)
        if "refused the recipient" in str(exc):
            print(
                "Africa's Talking sandbox: the number must be connected in AT's web Simulator"
                " (apps > SMS > Launch simulator > add number > Connect) before it can receive anything.",
                file=sys.stderr,
            )
        return 1

    if used == "console":
        print("OK (console mode): the message was logged with the CBODS-RESET-SMS marker.")
        print("Nothing was sent over a network. Set SMS_PROVIDER + credentials for a real send.")
    else:
        print(f"OK: accepted by {used} for {phone}. Ask the recipient to confirm arrival.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
