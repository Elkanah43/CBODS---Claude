"""Custom email backends.

Two classes, both small:

* ``LoggingConsoleEmailBackend`` — the console backend, plus one extra log
  line behind a fixed marker whenever a password reset link passes through,
  so a demonstrator can find the link with a search of a busy log.

* ``RetryingSMTPBackend`` — the real SMTP backend, with a single retry of
  the connection establishment step. Some networks intermittently stall the
  initial SMTP connect (the server never answers its banner), which Django
  reports as a failed send even though the transient moment has passed. A
  retry here costs one extra attempt and can never duplicate a message: if
  the connection could not be established, nothing was sent.
"""
import logging
import re

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPEmailBackend

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
    """SMTP backend that retries connection establishment once on failure."""

    def open(self):
        try:
            return super().open()
        except OSError:
            # open() left a partially configured connection behind; drop it
            # before trying again. (A connection that never completed can
            # have sent nothing, so the retry cannot duplicate a message.)
            if self._partial_connection is not None:
                self._close_connection(self._partial_connection)
                self._partial_connection = None
            self.connection = None
            return super().open()
