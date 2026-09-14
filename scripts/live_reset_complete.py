"""Complete the password-reset loop against the running app.

Follows a delivered reset link (https -> http for the local dev server),
submits a new password, then logs in with it and confirms the old password
no longer works. Usage:

    python scripts\\live_reset_complete.py <reset-link> <new-password> [username]

The username defaults to 'brevo_demo'. Requires the app from
`python scripts\\run_with_brevo.py` to be running on 127.0.0.1:8000.

Django's PasswordResetConfirmView redirects a valid token to
.../<uid>/set-password/ (so the token never appears in a Referer header), so
the driver follows that redirect and submits the form at the final URL.
"""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8000"
UA = "cbods-live-check/1.0"
OLD_PASSWORD = "Verify!23456789"  # the password the brevo_demo user was seeded with


def new_session():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def get(opener, path):
    req = urllib.request.Request(path, headers={"User-Agent": UA})
    with opener.open(req, timeout=30) as resp:
        return resp.status, resp.geturl(), resp.read().decode("utf-8", errors="replace")


def post(opener, path, data, referer):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        path, data=body, headers={"User-Agent": UA, "Referer": referer}
    )
    try:
        with opener.open(req, timeout=60) as resp:
            return resp.status, resp.geturl(), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", ""), ""


def csrf(html):
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    return match.group(1) if match else None


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: live_reset_complete.py <reset-link> <new-password> [username]")
    link = sys.argv[1].replace("https://", "http://", 1)
    new_password = sys.argv[2]
    username = sys.argv[3] if len(sys.argv) > 3 else "brevo_demo"
    if not link.startswith(BASE):
        sys.exit(f"link host is not the local app: {link}")

    # --- 1. open the reset link (follows the token -> set-password redirect)
    opener, _ = new_session()
    status, final_url, html = get(opener, link)
    print(f"[1/4] GET reset link -> {status} -> {final_url.replace(BASE, '')}")
    if status != 200 or "new password" not in html.lower():
        sys.exit("FAIL: the reset link did not render the set-password form "
                 "(expired? already used?).")
    token = csrf(html)
    if not token:
        sys.exit("FAIL: no CSRF token on the set-password form")

    # --- 2. submit the new password at the set-password URL --------------
    status, final_url, _ = post(
        opener, final_url,
        {"csrfmiddlewaretoken": token,
         "new_password1": new_password, "new_password2": new_password},
        final_url,
    )
    print(f"[2/4] POST new password -> {status} -> {final_url.replace(BASE, '')}")
    # urllib follows the success redirect (302 -> GET), so the final URL
    # landing on the "done" page is the signal, not the intermediate status.
    if "reset/done" not in final_url:
        sys.exit("FAIL: password change was not accepted.")

    # --- 3. log in with the NEW password --------------------------------
    status, _, html = get(opener, BASE + "/accounts/login/")
    token = csrf(html)
    status, final_url, _ = post(
        opener, BASE + "/accounts/login/",
        {"csrfmiddlewaretoken": token, "username": username, "password": new_password},
        BASE + "/accounts/login/",
    )
    print(f"[3/4] login with new password -> {status} -> {final_url.replace(BASE, '')}")
    if status != 302 or "dashboard" not in final_url:
        sys.exit("FAIL: could not log in with the new password.")

    # --- 4. OLD password must fail (fresh session, no cookies) ----------
    fresh, _ = new_session()
    status, _, html = get(fresh, BASE + "/accounts/login/")
    token = csrf(html)
    status, _, _ = post(
        fresh, BASE + "/accounts/login/",
        {"csrfmiddlewaretoken": token, "username": username, "password": OLD_PASSWORD},
        BASE + "/accounts/login/",
    )
    old_failed = status == 200
    print(f"[4/4] login with OLD password -> {status} (rejected: {old_failed})")

    print()
    if old_failed:
        print(f"PASSWORD RESET LOOP COMPLETE: '{username}' logs in with the new "
              "password; the old one is rejected.")
    else:
        sys.exit("WARN: the old password still worked!")


if __name__ == "__main__":
    main()