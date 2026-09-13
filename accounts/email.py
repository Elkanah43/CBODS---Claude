"""Custom email backends.

Three classes, all small:

* ``LoggingConsoleEmailBackend`` — the console backend, plus one extra log
  line behind a fixed marker whenever a password reset link passes through,
  so a demonstrator can find the link with a search of a busy log.

* ``RetryingSMTPBackend`` — the real SMTP backend, with a bounded retry of
  the connection establishment step. Some networks intermittently stall the
  initial SMTP connect (the server never answers its banner): on this
  machine's link to smtp-relay.brevo.com, roughly half of the plain-socket
  connects timed out (smtplib raises ``SMTPServerDisconnected`` after the
  full ``EMAIL_TIMEOUT``), while an immediate retry got through. Because
  Django's reset views call ``send_mail(..., fail_silently=True)``, an
  un-retried stall means the request returns success and the email is simply
  lost — the retry loop exists so the user's next attempt is not the fix.
  A connection that never completed can have sent nothing, so retries can
  never duplicate a message.

* ``BrevoHTTPSBackend`` — the same Brevo relay over its HTTPS API instead of
  SMTP, for networks that block or stall port 587 outright (outbound SMTP is
  a favourite botnet vector, so campus and hotel Wi-Fi routinely filter it).
  Same no-third-party-packages rule as ``accounts.sms``: the API speaks JSON
  over HTTPS and urllib is enough.
"""
import html
import json
import logging
import re
import smtplib
import socket
import time
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend
from django.core.mail.message import sanitize_address

logger = logging.getLogger("cbods.email")

# Matches the confirm URL as password_reset_email.txt renders it.
RESET_LINK = re.compile(r"https?://\S+/accounts/reset/[^/\s]+/[^/\s]+/")

MARKER = "CBODS-RESET-LINK"


class LoggingConsoleEmailBackend(ConsoleEmailBackend):
    def send_messages(self, email_messages):
        for message in email_messages:
            match = RESET_LINK.search(message.body or "")
            if match:
                # Warning rather than info: with no logging configuration the
                # root handler only emits warnings and above, and this has to
                # show up on a host we do not configure.
                logger.warning("%s %s %s", MARKER, ", ".join(message.to), match.group(0))
        return super().send_messages(email_messages)


class RetryingSMTPBackend(SMTPEmailBackend):
    """SMTP backend that retries connection establishment.

    Django's ``open()`` covers three distinct steps: TCP connect, STARTTLS
    and AUTH LOGIN. The stall this network hits happens during the connect
    step, so the retry loop re-runs only ``open()`` (bounded, with short
    pauses) and only for the transient-stall family (timeout, dropped
    connection, server gone mid-handshake). Everything else — an
    authentication rejection above all — propagates untouched, because no
    number of retries turns a bad password into a good one. (``SMTPException``
    subclasses ``OSError``, so catching that would sweep auth failures into
    the retry loop.)
    """

    # Attempts = 1 first try + 3 retries: observed stall rate is ~50% per
    # connect, so 4 attempts make an all-stall run unlikely (~6%) while the
    # worst-case wait stays EMAIL_TIMEOUT * 4 (+ pauses), not unbounded.
    MAX_ATTEMPTS = 4

    # Backoff between attempts. The stall clears within a second of retrying,
    # so pauses stay short; the sleeps run before attempts 2..n.
    RETRY_DELAYS = (0.5, 1.0, 2.0)

    def open(self):
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                return super().open()
            except (socket.timeout, ConnectionError, smtplib.SMTPServerDisconnected) as exc:
                # Django's open() leaves a partially configured connection
                # behind on failure; drop it before trying again. (A
                # connection that never completed can have sent nothing, so
                # the retry cannot duplicate a message.)
                if self._partial_connection is not None:
                    self._close_connection(self._partial_connection)
                    self._partial_connection = None
                self.connection = None
                if attempt == self.MAX_ATTEMPTS:
                    logger.warning(
                        "SMTP connection to %s:%s failed after %d attempts: %s",
                        self.host, self.port, attempt, exc,
                    )
                    raise
                delay = self.RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "SMTP connection to %s:%s failed (attempt %d/%d): %s; "
                    "retrying in %.1fs",
                    self.host, self.port, attempt, self.MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)


# The transient family on the HTTP side: the request never reached a working
# server (425/408) or Brevo is shedding load (429, 5xx). Everything else —
# 401/403 bad or expired key, 400 malformed payload, 402 out of daily credit —
# is a configuration or budget problem that no retry can fix.
RETRYABLE_HTTP_CODES = frozenset({408, 425, 429}) | set(range(500, 600))


class BrevoAPIError(Exception):
    """A Brevo API send failed. ``retryable`` marks the transient family."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class BrevoHTTPSBackend(BaseEmailBackend):
    """Send through Brevo's transactional-email HTTPS API.

    One POST per message to ``/v3/smtp/email`` with the ``api-key`` header; a
    201 whose body carries ``messageIds`` is the success verdict. Credentials
    come from ``settings.BREVO_API_KEY`` — the API key (``xkeysib-…``) from
    Settings → SMTP & API → API, *not* the SMTP key (``xsmtpsib-…``), which
    the API answers with 401.

    The retry loop covers only the unreachable/overloaded family: the request
    never reached a working server, or Brevo answered 429/5xx. Retries reuse
    the exact same payload — and unlike the SMTP connect stall, an HTTP send
    *can* have succeeded while its response was lost, and Brevo honours an
    idempotency key only for batch (``messageVersions``) sends, so a small
    duplicate risk is accepted here in exchange for not losing the message.
    Production errors (401 bad key, 400 bad payload, 402 budget) propagate on
    the first attempt.
    """

    API_URL = "https://api.brevo.com/v3/smtp/email"

    # Same shape as RetryingSMTPBackend: 1 first try + 3 retries, short
    # pauses, so the worst case stays bounded.
    MAX_ATTEMPTS = 4
    RETRY_DELAYS = (0.5, 1.0, 2.0)

    def __init__(self, *args, **kwargs):
        # BaseEmailBackend only sets fail_silently, so pick up our kwargs
        # first (as Django's own backends do): an explicit api_key (e.g. via
        # get_connection(...)) wins over the setting, and timeout gets a
        # bounded default — timeout=None would wait forever, where a bounded
        # wait surfaces as an error the retry loop can work with.
        self.api_key = kwargs.pop("api_key", None) or getattr(settings, "BREVO_API_KEY", "")
        self.timeout = kwargs.pop("timeout", None) or 15
        super().__init__(*args, **kwargs)
        self.api_url = self.API_URL

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            try:
                self._send_with_retries(message)
            except BrevoAPIError as exc:
                if not self.fail_silently:
                    raise
                # Same contract as Django's backends: fail_silently keeps the
                # caller working, the log keeps it diagnosable.
                logger.warning(
                    "Brevo send to %s failed: %s", ", ".join(message.to), exc
                )
            else:
                sent += 1
        return sent

    def _send_with_retries(self, message):
        payload = self._payload(message)
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                # Return, not fall through: the loop must end the moment a
                # POST is accepted, or a success would be POSTed four times.
                return self._post(payload)
            except BrevoAPIError as exc:
                if not exc.retryable or attempt == self.MAX_ATTEMPTS:
                    logger.warning(
                        "Brevo send to %s failed after %d attempt(s): %s",
                        ", ".join(message.to), attempt, exc,
                    )
                    raise
                delay = self.RETRY_DELAYS[attempt - 1]
                logger.warning(
                    "Brevo send to %s failed (attempt %d/%d): %s; "
                    "retrying in %.1fs",
                    ", ".join(message.to), attempt, self.MAX_ATTEMPTS, exc, delay,
                )
                time.sleep(delay)

    def _payload(self, message):
        """EmailMessage -> Brevo's JSON body (sender/to/subject required)."""
        encoding = message.encoding
        sender = self._addr(message.from_email or settings.DEFAULT_FROM_EMAIL, encoding)
        to = [self._addr(a, encoding) for a in message.to if a]
        cc = [self._addr(a, encoding) for a in message.cc if a]
        bcc = [self._addr(a, encoding) for a in message.bcc if a]
        if not (to or cc or bcc):
            raise BrevoAPIError("message has no recipients")
        # Brevo requires a "to" entry even for bcc-only messages; the sender
        # is the least-surprising stand-in (it receives its own message).
        payload = {
            "sender": sender,
            "to": to or [sender],
            "subject": message.subject or "",
        }
        if cc:
            payload["cc"] = cc
        if bcc:
            payload["bcc"] = bcc
        if message.reply_to:
            payload["replyTo"] = [
                self._addr(a, encoding) for a in message.reply_to if a
            ]
        # Plain text is what every message in this app is; keep Brevo's
        # textContent the single body so links stay links. An attachment forces
        # the multipart-MIME world the API does not cover with textContent
        # alone: wrap the body in a <pre> htmlContent so the text still arrives
        # (Brevo requires at least one content field alongside attachments).
        if message.attachments:
            payload["htmlContent"] = "<pre>{}</pre>".format(html.escape(message.body or ""))
        elif message.body:
            payload["textContent"] = message.body
        if message.extra_headers:
            payload["headers"] = {
                str(k): str(v) for k, v in message.extra_headers.items()
            }
        return payload

    @staticmethod
    def _addr(raw, encoding="utf-8"):
        """'Name <local@domain>' or ('Name', 'addr') -> Brevo's {email, name}.

        The display name is taken from the raw input so a non-ASCII name
        reaches Brevo as readable UTF-8 (sanitize_address would MIME-encode
        it for the SMTP header world). The address itself goes through
        sanitize_address, which validates it — raising ValueError on junk —
        and applies IDNA to the domain, exactly as Django's SMTP path does.
        """
        if isinstance(raw, tuple):
            name, addr = str(raw[0]), str(raw[1])
        else:
            name, addr = parseaddr(str(raw or ""))
        try:
            addr = sanitize_address(addr, encoding)
        except ValueError as exc:
            raise BrevoAPIError(str(exc)) from exc
        if not addr or "@" not in addr:
            raise BrevoAPIError(f"cannot parse email address {raw!r}")
        return {"email": addr, "name": " ".join(name.split()) or None}

    def _post(self, payload):
        """One API call. Returns the messageIds; raises BrevoAPIError."""
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            # HTTPError is both URLError and OSError, so it is caught first.
            # Debug, not warning: the retry loop logs one attempt-level line
            # per failure already, and the body is only wanted when digging.
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            logger.debug(
                "Brevo API HTTP %s from %s: %s", exc.code, self.api_url, detail
            )
            raise BrevoAPIError(
                f"Brevo API returned HTTP {exc.code}",
                retryable=exc.code in RETRYABLE_HTTP_CODES,
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Covers DNS failure, refused connect, TLS failure, mid-read
            # drops and the timeout itself: nothing reached a working server.
            logger.debug("Brevo API unreachable at %s: %s", self.api_url, exc)
            raise BrevoAPIError("Brevo API unreachable", retryable=True) from exc
        message_ids = data.get("messageIds") if isinstance(data, dict) else None
        if not message_ids:
            # An accepted send answers 201 with messageIds; their absence is
            # logged, not retried — the request plainly got through.
            logger.warning(
                "Brevo API response carried no messageIds: %s", str(data)[:200]
            )
        return message_ids or []
