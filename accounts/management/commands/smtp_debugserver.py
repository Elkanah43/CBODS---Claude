"""Local SMTP sink for developing and demonstrating real email delivery.

Runs a minimal RFC 5321 server (pure standard library — no third-party
dependencies) that accepts anything it is handed and prints every message to
the console. Nothing is relayed or delivered anywhere — it is a mailbox on
your own machine.

Point the project at it with a single environment variable:

    set EMAIL_HOST=localhost
    python manage.py smtp_debugserver        # listens on :25
    python manage.py runserver               # other terminal

Any password reset or notification the app sends then arrives here, where the
link can be copied straight out of the printed message. For an unauthenticated
sink only EMAIL_HOST is needed; the backend sends no AUTH when no credentials
are set.

The default port is 25, matching settings.py's EMAIL_PORT default. It needs
no special privilege on Windows; on Unix, ports below 1024 typically do — pass
--port 1025 there and set EMAIL_PORT to match.

Why not aiosmtpd? aiosmtpd's threaded controller is the usual choice, but its
startup proved unreliable on some Windows hosts (binds but never serves). A
plain synchronous socket server cannot exhibit that failure mode, and the SMTP
subset smtplib actually needs is small enough to implement safely here.
"""
import socketserver

from django.core.management.base import BaseCommand, CommandError


class SinkSMTPHandler(socketserver.StreamRequestHandler):
    """Speaks just enough RFC 5321 for smtplib to hand over a message."""

    def handle(self):
        self.mail_from = ""
        self.rcpt_tos = []
        try:
            self.send("220 localhost ESMTP CBODS sink ready")
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                if not self.dispatch(line.rstrip(b"\r\n")):
                    return
        except OSError:
            # Client went away mid-conversation (e.g. app shut down); drop it.
            return

    # -- protocol helpers -------------------------------------------------

    def send(self, text):
        self.wfile.write(text.encode("ascii") + b"\r\n")
        self.wfile.flush()

    def dispatch(self, line):
        upper = line.upper()
        if upper.startswith(b"EHLO "):
            self.send("250-localhost")
            self.send("250 SIZE 33554432")
        elif upper.startswith(b"HELO "):
            self.send("250 localhost")
        elif upper.startswith(b"MAIL FROM:"):
            self.mail_from = line[10:].strip().decode("ascii", errors="replace")
            self.send("250 OK")
        elif upper.startswith(b"RCPT TO:"):
            self.rcpt_tos.append(line[8:].strip().decode("ascii", errors="replace"))
            self.send("250 OK")
        elif upper == b"DATA":
            return self.read_data()
        elif upper == b"QUIT":
            self.send("221 Bye")
            return False
        elif upper.startswith(b"RSET") or upper.startswith(b"NOOP"):
            self.send("250 OK")
        elif upper.startswith(b"VRFY"):
            self.send("252 Cannot VRFY, but will accept the message")
        else:
            self.send("500 Command unrecognized")
        return True

    def read_data(self):
        self.send("354 End data with <CR><LF>.<CR><LF>")
        content = []
        while True:
            line = self.rfile.readline()
            if not line:
                return False
            if line.rstrip(b"\r\n") == b".":
                break
            content.append(line)
        envelope = {
            "mail_from": self.mail_from,
            "rcpt_tos": list(self.rcpt_tos),
            "content": b"".join(content),
        }
        self.server.messages.append(envelope)
        peer = self.client_address[0] if self.client_address else "?"
        print(
            "\n========== MESSAGE RECEIVED ==========\n"
            f"From:    {self.mail_from}\n"
            f"To:      {', '.join(self.rcpt_tos)}\n"
            f"Peer:    {peer}\n"
            f"{envelope['content'].decode('utf-8', errors='replace')}"
            "======================================\n",
            flush=True,
        )
        self.send("250 Message accepted for delivery")
        return True


class SinkSMTPServer(socketserver.ThreadingTCPServer):
    """Accepts any message; stores envelopes in ``.messages`` and prints them."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address):
        super().__init__(server_address, SinkSMTPHandler)
        self.messages = []


class Command(BaseCommand):
    help = (
        "Run a local SMTP debug server that accepts and prints every message "
        "(delivers nothing). Pair with EMAIL_HOST=localhost."
    )

    def add_arguments(self, parser):
        parser.add_argument("--addr", default="127.0.0.1",
                            help="Interface to listen on (default 127.0.0.1)")
        parser.add_argument("--port", type=int, default=25,
                            help="Port to listen on (default 25, matching "
                                 "settings.py's EMAIL_PORT default)")

    def handle(self, *args, **options):
        addr, port = options["addr"], options["port"]
        try:
            server = SinkSMTPServer((addr, port))
        except OSError as exc:
            raise CommandError(
                f"cannot bind {addr}:{port} — {exc}. If the port is in use, "
                "pass --port 1025 and set EMAIL_PORT=1025."
            ) from exc
        self.stdout.write(self.style.SUCCESS(
            f"SMTP debug sink listening on {addr}:{port} — waiting for mail "
            "(Ctrl+C to stop). Messages are printed below; nothing is delivered."
        ))
        try:
            server.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            self.stdout.write("\nStopped SMTP debug sink.")
        finally:
            server.server_close()