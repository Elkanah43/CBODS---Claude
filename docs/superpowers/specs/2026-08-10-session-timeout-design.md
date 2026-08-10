# Idle Session Timeout — Design

**Date:** 2026-08-10
**Status:** Approved (design review), pending implementation

## Goal

Automatically end a logged-in session after 15 minutes of inactivity and
return the user to the login screen, with a one-minute countdown warning
before the logout.

## Decisions (agreed with user)

- **Timeout model:** idle timeout — the clock resets on every click/request.
- **Duration:** 15 minutes (OWASP ASVS v4.2 recommends ≤15 min for
  high-value apps; standard for health systems holding protected data).
- **Warning:** a countdown banner appears 1 minute before expiry with a
  "Stay signed in" button.

## Approach

Django-native session expiry plus a small vanilla-JS countdown. No new
endpoints, no new dependencies (Bootstrap bundle already vendored).

## Implementation

### 1. `cbods/settings.py`

```python
# Idle session timeout: 15 minutes without a request logs the user out.
# SESSION_SAVE_EVERY_REQUEST rolls the deadline forward on every request
# (cookie max-age and DB expire_date both refresh), giving a true idle
# timeout rather than a fixed one from login.
SESSION_COOKIE_AGE = 15 * 60
SESSION_SAVE_EVERY_REQUEST = True
```

Verified against the vendored Django source: `get_expiry_date()` recomputes
`now + SESSION_COOKIE_AGE` on every save when the stored expiry is a plain
age (which it is after `auth.login` calls `set_expiry(SESSION_COOKIE_AGE)`),
so the deadline genuinely rolls with each request. `load()` does not restore
a fixed timestamp from the DB, so the roll is not lost across requests.
Enforcement is cookie-driven: with the max-age refreshed per request, the
browser drops `sessionid` 15 minutes after the last request, and the next
request to a `@login_required` view redirects to login.

### 2. `templates/base.html`

- On the `<body>` tag, when `user.is_authenticated`, add
  `data-session-deadline="{{ request.session.get_expiry_date|date:'U' }}"`
  — the server-authoritative rolling deadline as epoch seconds.
- Load `static/js/session-timeout.js` (deferred) only when authenticated.

### 3. `static/js/session-timeout.js` (new, vanilla JS)

- Reads the deadline from the body attribute; exits silently if absent
  (i.e. not authenticated).
- Maintains a `deadline` in ms. On user activity (click, keydown, touchstart,
  throttled to ~1/s) resets `deadline = now + SESSION_COOKIE_AGE` client-side
  — a mirror of the server roll; the user's next real request confirms it.
- At `deadline − 60s`: shows a non-blocking banner (Bootstrap styling,
  positioned fixed at the bottom) with a live `M:SS` countdown and a
  **Stay signed in** button that reloads the page — a real request, so the
  server genuinely extends the session and the banner disappears.
- At `deadline`: submits the existing logout form (POST + CSRF) → Django's
  `LogoutView` clears the session and redirects to `login`
  (`LOGOUT_REDIRECT_URL = 'login'` already set).

## Behavior

1. User logs in; 15-minute idle clock starts.
2. Any click/keystroke before expiry resets the clock (and the server rolls
   on the next request).
3. At 14:00 a banner counts down "Your session expires in 1:00".
   "Stay signed in" reloads the page and resets everything.
4. At 15:00 of no activity, the logout form is submitted automatically and
   the user lands on the login screen.

## Edge cases

- **JS disabled:** server-side cookie expiry still logs the user out on the
  next request; no proactive redirect or warning.
- **Multiple tabs:** each tab runs its own timer; harmless.
- **Session dies early** (e.g. cookie cleared): the next request redirects to
  login naturally; the client timer is just superseded.
- **Clock skew:** the deadline is computed server-side; client compares
  against local time, acceptable for a demo.

## Verification

- Run the project test suite (`manage.py test`) — no regressions.
- In the Preview tab, drive the page with a near-deadline value (via the
  browser console) to confirm the warning appears, the countdown ticks, and
  the automatic logout lands on the login screen.

## Out of scope

- "Remember me" / session-length choice per login.
- Server-push keepalive polling.
- Custom logout views.
