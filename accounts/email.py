"""Email backend that prints, and additionally flags password reset links.

Delivery is the console backend: nothing leaves the machine, the message is
written to the server log. That is workable locally, where the log is the
terminal you are already watching, but on a host the reset email is buried in
whatever else the process is writing.

This wraps that backend and emits one extra line carrying the link behind a
fixed marker, so the demonstrator can find it with a search rather than by
reading the log. Nothing about delivery changes.
"""
import logging
import re

from django.core.mail.backends.console import EmailBackend as ConsoleEmailBackend

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
