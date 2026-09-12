"""SMS sending for the phone-based password reset.

One function, ``send_sms``, sits between the OTP service and whichever
provider is configured. ``SMS_PROVIDER`` selects the backend:

* ``console`` (default) — prints to the log behind a fixed marker, the same
  trick ``LoggingConsoleEmailBackend`` uses for reset emails, so a demo works
  with no signup, no credit and no network at all.
* ``sasusync`` — POST to SasuSync's send endpoint (prepaid Ghanaian gateway,
  free sandbox, mobile-money top-up).
* ``africastalking`` — POST to Africa's Talking, which is on PythonAnywhere
  free's allowlist, so the flow works there too when the time comes. Two
  AT quirks are handled below: the sandbox never texts a real handset (a
  number only receives anything once it is connected in AT's web Simulator),
  and the send API answers HTTP 201 even when delivery is refused — the
  per-recipient status inside the body, not the HTTP code, is the verdict.

No third-party packages are used: providers speak plain HTTPS with JSON and
urllib is enough. A provider outage raises ``SmsSendError`` and the caller
decides what the user sees, rather than an exception page.
"""
import json
import logging
import re
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger("cbods.sms")

SMS_MARKER = "CBODS-RESET-SMS"

# Ghana mobile prefixes: the digit after 233/0 is 2, 5, or 7 per NCA ranges
# (24/54/20/50/27/57/26/56/23/59/25/53...). Enforcing a single leading digit
# would reject real numbers; 2/5/7 covers all mobile allocations.


class SmsSendError(Exception):
    """A provider refused or could not be reached. Never leaks provider detail."""


def normalize_ghana_phone(raw):
    """Coerce the many shapes of a Ghanaian number to +233XXXXXXXXX.

    Handles the forms this system actually stores and users actually type:
    ``024-000-0001`` (seed/demo data), ``0240000001`` (local), ``233240000001``
    (no plus), ``+233 24 000 0001`` (spaces), ``+233240000001`` (full). Any
    other country code, or a local number that does not start with a valid
    Ghana prefix, is rejected with ValueError rather than silently sent
    somewhere wrong.

    Ghana numbers: +233 followed by 9 digits (the mobile prefix without its
    leading zero, e.g. 24/54/20/50, plus 7 more).
    """
    if not raw:
        raise ValueError("no phone number given")
    digits = re.sub(r"[\s\-().]", "", raw.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("00233"):
        digits = digits[5:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "233" + digits[1:]
    if not digits.startswith("233"):
        raise ValueError(f"not a Ghana number: {raw!r}")
    rest = digits[3:]
    if len(rest) != 9 or not rest.isdigit():
        raise ValueError(f"not a Ghana mobile number: {raw!r}")
    return "+233" + rest


def send_sms(phone_e164, text):
    """Send ``text`` to ``phone_e164`` via the configured provider.

    Returns the provider's own name on success. Raises SmsSendError on
    failure; the HTTP details stay in the log, not on the user's screen.
    """
    provider = getattr(settings, "SMS_PROVIDER", "console").lower()
    try:
        if provider == "console":
            _send_console(phone_e164, text)
        elif provider == "sasusync":
            _send_sasusync(phone_e164, text)
        elif provider == "africastalking":
            _send_africastalking(phone_e164, text)
        else:
            raise SmsSendError(f"unknown SMS_PROVIDER {provider!r}")
    except SmsSendError:
        raise
    except Exception as exc:  # provider libraries, network stack, anything
        logger.warning("SMS send to %s failed: %s", phone_e164, exc)
        raise SmsSendError("SMS provider request failed") from exc
    return provider


def _send_console(phone_e164, text):
    # Warning level, like the email marker: the root handler emits warnings
    # and above by default, and a demonstrator must be able to find this.
    logger.warning("%s %s %s", SMS_MARKER, phone_e164, text)


def _post_json(url, headers, payload, timeout=15):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        logger.warning("SMS provider HTTP %s from %s: %s", exc.code, url, detail)
        raise SmsSendError(f"SMS provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("SMS provider unreachable at %s: %s", url, exc)
        raise SmsSendError("SMS provider unreachable") from exc
    return data


def _send_sasusync(phone_e164, text):
    api_key = settings.SASUSYNC_API_KEY
    if not api_key:
        raise SmsSendError("SASUSYNC_API_KEY is not set")
    # Endpoint per SasuSync's quick-start. Their sandbox is configured on the
    # account/key side; if their docs give a sandbox base URL, set it via
    # SASUSYNC_API_BASE rather than changing code.
    base = (settings.SASUSYNC_API_BASE or "https://sms.sasusync.com").rstrip("/")
    _post_json(
        f"{base}/api/v1/send",
        headers={"X-API-Key": api_key},
        payload={
            "sender": settings.SMS_SENDER_ID,
            "recipients": [phone_e164.replace("+", "")],
            "message": text,
        },
    )


def _send_africastalking(phone_e164, text):
    api_key = settings.AT_API_KEY
    username = settings.AT_USERNAME
    if not api_key or not username:
        raise SmsSendError("AT_API_KEY / AT_USERNAME are not set")
    host = "https://api.sandbox.africastalking.com" if settings.AT_SANDBOX else "https://api.africastalking.com"
    data = _post_json(
        f"{host}/version1/messaging",
        headers={"apiKey": api_key, "Accept": "application/json"},
        payload={
            "username": username,
            "to": [phone_e164],
            "message": text,
            "from": settings.SMS_SENDER_ID or None,
            "enqueue": 1,
        },
    )
    # AT answers HTTP 201 even when no recipient can receive — in sandbox
    # mode, any number not connected in their web Simulator comes back as
    # DeliveryFailure. The per-recipient status is the real verdict: log
    # every refusal, and fail the send when nothing went out at all, so the
    # view never tells a user to "check their phone" when no text is coming.
    recipients = ((data.get("SMSMessageData") or {}).get("Recipients")) or []
    for recipient in recipients:
        if str(recipient.get("statusCode")) != "101":  # 101 = Success
            logger.warning(
                "AT did not deliver to %s: status %s %s%s",
                recipient.get("number"),
                recipient.get("statusCode"),
                recipient.get("status"),
                " (sandbox? connect the number in AT's Simulator)" if settings.AT_SANDBOX else "",
            )
    if recipients and all(str(r.get("statusCode")) != "101" for r in recipients):
        raise SmsSendError("SMS provider refused the recipient")
    if not recipients:
        logger.warning("AT response carried no per-recipient status: %s", str(data)[:200])
