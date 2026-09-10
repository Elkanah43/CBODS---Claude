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
7. **Transient network stall.** This machine has intermittently stalled SMTP
   connects; the app retries the connection once via
   `accounts.email.RetryingSMTPBackend`. A single retry usually suffices — a
   rare second failure just means asking for the reset again.
8. **No email account on the user?** The user row's email field is empty —
   nothing is sent by design (and the reset flow reveals nothing about it).

**Fallback when email cannot work at all:** an admin can open the user in
`/admin/` and use the built-in **Reset password** button to set a new password
directly — no email involved — or use the admin "Send password-reset link"
action once email is healthy again.