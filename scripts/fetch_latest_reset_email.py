"""Fetch and print the latest delivered password-reset email from Gmail.

Reads credentials from scripts/.gmail_imap_creds (address on line 1, Gmail
app password on line 2 — the app password authorizes both SMTP and IMAP on
the same account) or from env vars GMAIL_IMAP_USER / GMAIL_IMAP_PASSWORD.

Only the most recent message whose subject is 'Reset your CBODS password' is
read; nothing else in the inbox is touched. Gmail's IMAP SUBJECT search is
unreliable (it can miss brand-new messages), so the script lists the newest
messages by UID and filters client-side instead. Prints headers and the full
plain-text body so the rendered https link, username, and expiry wording can
be checked against the template.

Usage:
    python scripts\\fetch_latest_reset_email.py [max_to_scan]
"""
import email
import imaplib
import os
import sys
from pathlib import Path

CREDS_FILE = Path(__file__).resolve().parent / ".gmail_imap_creds"
TARGET_SUBJECT = "Reset your CBODS password"


def load_credentials():
    user = os.environ.get("GMAIL_IMAP_USER", "").strip()
    password = os.environ.get("GMAIL_IMAP_PASSWORD", "").strip()
    if (not user or not password) and CREDS_FILE.exists():
        lines = [ln.strip() for ln in CREDS_FILE.read_text(encoding="utf-8")
                 .splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if len(lines) >= 2:
            user, password = lines[0], lines[1]
    return user, password


def main():
    user, password = load_credentials()
    if not user or not password:
        sys.exit("Missing credentials: set GMAIL_IMAP_USER/GMAIL_IMAP_PASSWORD "
                 "or create scripts/.gmail_imap_creds (address, then app "
                 "password).")
    if " " in password and len(password) != 16:
        print("NOTE: remove spaces from the app password if you pasted the "
              "16-char groups as-is.")

    conn = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=60)
    try:
        conn.login(user, password)
        conn.select("INBOX")
        # List everything, then filter client-side: reliable regardless of
        # Gmail's server-side SUBJECT search indexing.
        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            sys.exit("No messages in the inbox.")
        uids = data[0].split()
        # Walk backwards from the newest until we find the reset email.
        for uid in reversed(uids):
            typ, msg_data = conn.fetch(
                uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT DATE MESSAGE-ID)])"
            )
            if typ != "OK":
                continue
            hdr = email.message_from_bytes(msg_data[0][1])
            subject = hdr["Subject"] or ""
            if subject.strip() == TARGET_SUBJECT:
                typ, full = conn.fetch(uid, "(RFC822)")
                raw = full[0][1]
                msg = email.message_from_bytes(raw)
                break
        else:
            sys.exit(f"No email with subject '{TARGET_SUBJECT}' found.")
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    print("From     :", msg["From"])
    print("To       :", msg["To"])
    print("Subject  :", msg["Subject"])
    print("Date     :", msg["Date"])
    print("Message-ID:", msg["Message-ID"])
    print("\n" + "=" * 36 + " FULL EMAIL BODY " + "=" * 36)
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", errors="replace")
                print(body)
                break
    else:
        print(msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"))
    print("=" * 88)


if __name__ == "__main__":
    main()