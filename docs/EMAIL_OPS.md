# Email ops note (Brevo)

Short runbook for the email relay. Covers the free tier, key rotation, and
what to do when a password-reset email does not arrive.

## Brevo free tier

| Item | Value |
|---|---|
| Daily send limit | **300 emails/day** (transactional + campaigns together), resets daily |
| Cost | Free forever, no credit card |
| Sender requirement | A verified sender address (Settings → Senders) — your signup email works |
| Domain | Optional. Freemail senders (gmail.com etc.) work, but Brevo rewrites the From domain to `*.brevosend.com` and Google/Yahoo/Microsoft compliance warnings (DKIM/DMARC) appear in the dashboard. A verified custom domain removes both. |

Every password reset and notification the app sends counts against the 300/day
budget. A demo that runs several resets is fine; a busy deployment should
watch Brevo's SMTP statistics for the day.

## HTTPS API instead of SMTP

When the network blocks or stalls port 587 (campus and hotel Wi-Fi often do),
set `BREVO_API_KEY` to an **API** key (`xkeysib-…`, Settings → SMTP & API →
API tab — the SMTP key answers 401 there) and the app sends every message with
one POST to Brevo's transactional API instead of opening SMTP sessions.
`EMAIL_HOST` wins if both are set. Checks and limits are the same as the SMTP
relay's: verified sender, 300/day free-tier budget, reset links included in
the message body. Retries cover only the transient family — unreachable,
HTTP 429 and 5xx — up to 4 attempts with short pauses (`Brevo send to ...
failed (attempt n/4)` lines in the log); a 401/402/400 fails on the first
attempt because no retry turns a bad key or an empty budget into a good one.

Prove the setup works before a demo: `python scripts\verify_live_api.py
you@example.com` sends a test email and a real password reset through this
backend (credentials from the environment or `scripts/.api_creds`:
`api_key=…`, `from=…`).

## SMTP key lifecycle and rotation

- **Where**: Settings → SMTP & API → SMTP tab. `EMAIL_HOST_USER` is the SMTP
  login shown there; `EMAIL_HOST_PASSWORD` is the SMTP key (starts with
  `xsmtpsib-`). Use the SMTP key, **not** an API key (`xkeysib-`).
- **Expiry**: keys expire at the chosen expiry (default 1 year) **or after
  90 days of inactivity, whichever comes first**. A key that sat unused will
  stop authenticating even though its expiry date is in the future.
- **Rotation procedure** (no downtime, no lost resets):
  1. Generate a new SMTP key (Settings → SMTP & API → SMTP → Generate a new
     SMTP key).
  2. Update the secret in both places it lives:
     - `scripts/.smtp_creds` → `password=` line (used by
       `scripts/verify_live_smtp.py` and `scripts/run_with_brevo.py`)
     - the terminal's `EMAIL_HOST_PASSWORD` env var (used by `runserver` /
       the deployed process)
  3. Prove the new key works **before** touching the old one:
     `python scripts\verify_live_smtp.py` must print both sends accepted.
  4. Only then delete the old key in Brevo. If the new key is wrong, the old
     one still works and nothing is locked out.

## Reset email does not arrive — checklist

Work down in this order:

1. **Did the app send at all?** Search the runserver log for
   `Failed to send password reset email`. Absent = the relay accepted the
   message; the problem is downstream. Present = a send error follows the
   line; read it (see steps 4–6).
2. **Is `EMAIL_HOST` set?** Without it the app uses the console backend:
   nothing is emailed, and the message (link included) prints to the server
   terminal behind the `CBODS-RESET-LINK` marker — search the log for that
   marker.
3. **Spam folder.** The email may have been delivered but filtered. Since the
   sender is the account's own verified address this is unlikely, but check.
4. **Sender still verified?** Settings → Senders: the From address must show
   `Verified`. An unverified sender makes Brevo reject the message at send
   time (visible in the log traceback).
5. **Key valid / not expired?** An expired key (see rotation above) surfaces
   as an authentication failure in the send error. Rotate per the procedure.
6. **Daily limit hit?** Brevo's SMTP statistics page shows today's usage.
   Over 300/day, sends are refused or queued.
7. **Transient network stall.** This machine's link to the relay has been
   observed dropping about half of plain SMTP connects (the server never
   answers its banner; smtplib times out after `EMAIL_TIMEOUT` seconds). The
   app retries the connection up to 4 attempts with short pauses via
   `accounts.email.RetryingSMTPBackend` — check the runserver log for its
   `SMTP connection to ... failed (attempt n/4)` lines. A `failed after 4
   attempts` line means the send was lost; ask for the reset again, or run
   `python scripts\verify_live_smtp.py` to see the raw errors. When SMTP is
   simply unusable on the network, switch to Brevo's HTTPS API (section above):
   it rides the same port as the web app itself.
8. **No email account on the user?** The user row's email field is empty —
   nothing is sent by design (and the reset flow reveals nothing about it).

**Fallback when email cannot work at all:** an admin can open the user in
`/admin/` and use the built-in **Reset password** button to set a new password
directly — no email involved — or use the admin "Send password-reset link"
action once email is healthy again.