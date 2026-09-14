"""Verify the real SMTP backend end to end.

Runs entirely in one process, deterministically (no asyncio, no subprocess):

  1. starts the stdlib SMTP sink (the same SinkSMTPServer the
     ``smtp_debugserver`` management command uses) on a free port,
  2. configures Django settings for EMAIL_HOST=<that host/port> exactly the
     way cbods/settings.py does from environment variables,
  3. sends a plain test message through django.core.mail,
  4. requests a password reset for a throwaway user via the test client,
  5. asserts both messages arrived at the sink, extracts the reset link from
     the delivered email, and follows it to the set-password form.

Settings are configured directly rather than via os.environ because settings.py
is imported before this script could set variables; the values mirror what
EMAIL_HOST=localhost + EMAIL_PORT=<port> produce.
"""
import os
import socket
import sys
import threading
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cbods.settings")

import django

django.setup()

from accounts.management.commands.smtp_debugserver import SinkSMTPServer
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.test import Client

User = get_user_model()

THROWAWAY = "smtp_verify_user"


def wait_for_banner(host, port, timeout=10.0):
    """Block until the sink answers with its 220 greeting."""
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=2) as probe:
                banner = probe.recv(64)
            if banner.startswith(b"220"):
                return banner
            last_error = OSError(f"unexpected banner: {banner!r}")
        except OSError as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"SMTP sink never answered on {host}:{port}: {last_error}")


def main():
    server = SinkSMTPServer(("127.0.0.1", 0))          # port 0: free port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]

    try:
        banner = wait_for_banner(host, port)
        print(f"sink listening on {host}:{port} | "
              f"{banner.decode(errors='replace').strip()}")

        from django.conf import settings
        # Mirror settings.py's env-var branch for EMAIL_HOST set:
        settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
        settings.EMAIL_HOST = host
        settings.EMAIL_PORT = port
        settings.EMAIL_HOST_USER = ""      # no AUTH for the sink
        settings.EMAIL_HOST_PASSWORD = ""
        settings.EMAIL_USE_TLS = False
        settings.EMAIL_USE_SSL = False
        settings.EMAIL_TIMEOUT = 15

        # --- 1. plain send through the real SMTP backend ----------------
        send_mail(
            subject="CBODS SMTP verification",
            message="If you can read this in the sink, Django's SMTP backend works.",
            from_email=None,  # DEFAULT_FROM_EMAIL
            recipient_list=["staff@example.com"],
        )
        assert len(server.messages) == 1, "plain send did not arrive at the sink"
        print(f"[1/3] plain send OK: from={server.messages[0]['mail_from']} "
              f"to={server.messages[0]['rcpt_tos']}")

        # --- 2. password reset flow over the same backend ----------------
        user = User.objects.create_user(
            username=THROWAWAY, email=f"{THROWAWAY}@example.com",
            password="Verify!23456789", role="PATIENT",
        )
        client = Client()
        response = client.post(
            "/accounts/password-reset/", {"email": user.email},
            HTTP_HOST="localhost",   # ALLOWED_HOSTS does not include testserver
        )
        assert response.status_code == 302, \
            f"reset request failed: {response.status_code}"
        assert len(server.messages) == 2, "reset email did not arrive at the sink"
        body = server.messages[1]["content"].decode("utf-8", errors="replace")
        recipients = server.messages[1]["rcpt_tos"]
        assert user.email in recipients or f"<{user.email}>" in recipients, \
            f"reset email went to the wrong recipient: {recipients}"
        link = next(
            (ln.strip() for ln in body.splitlines()
             if ln.strip().startswith("http") and "/accounts/reset/" in ln),
            None,
        )
        assert link, f"no reset link found in the delivered email:\n{body}"
        print(f"[2/3] password-reset email OK: to={user.email}")
        print(f"      link: {link}")

        # --- 3. the reset link itself works ------------------------------
        follow = client.get(link, follow=True, HTTP_HOST="localhost")
        assert follow.status_code == 200, \
            f"reset link did not resolve: {follow.status_code}"
        assert b"password" in follow.content.lower(), \
            "reset link did not render the set-password form"
        print("[3/3] reset link resolves to the set-password form OK")
    finally:
        server.shutdown()
        server.server_close()
        User.objects.filter(username=THROWAWAY).delete()

    print("\nSMTP VERIFICATION PASSED - the real SMTP backend delivered both messages.")


if __name__ == "__main__":
    main()