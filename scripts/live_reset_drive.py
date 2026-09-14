"""Drive the password-reset flow over HTTP against the running app.

Usage:
    python scripts\\live_reset_drive.py [email@example.com]
Defaults to the address in scripts/.smtp_creds (`from` or `user`, bare form).

Requires `python scripts\\run_with_brevo.py` to already be running on
127.0.0.1:8000. GETs the reset form, POSTs the address, follows the redirect,
and reports what the app did. The email itself is delivered by the relay; the
reset link comes from the recipient's inbox.
"""
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://127.0.0.1:8000"
UA = "cbods-live-check/1.0"


def _email():
    if len(sys.argv) > 1:
        return sys.argv[1]
    for raw in open(Path(__file__).resolve().parent / ".smtp_creds", encoding="utf-8"):
        line = raw.strip()
        if line.startswith("from="):
            value = line.split("=", 1)[1].strip()
            match = re.search(r"<([^<>]+)>", value)
            return match.group(1).strip() if match else value
    sys.exit("no recipient address found")


def main():
    email = _email()
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    # --- 1. fetch the form, grab the CSRF token -------------------------
    req = urllib.request.Request(
        BASE + "/accounts/password-reset/", headers={"User-Agent": UA}
    )
    with opener.open(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    print("GET  /accounts/password-reset/ ->", resp.status)
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
    if not match:
        sys.exit("FAIL: no CSRF token on the reset form")
    token = match.group(1)

    # --- 2. submit the address ------------------------------------------
    data = urllib.parse.urlencode(
        {"email": email, "csrfmiddlewaretoken": token}
    ).encode()
    req = urllib.request.Request(
        BASE + "/accounts/password-reset/",
        data=data,
        headers={"User-Agent": UA, "Referer": BASE + "/accounts/password-reset/"},
    )
    try:
        with opener.open(req, timeout=60) as resp:
            print("POST /accounts/password-reset/ ->", resp.status, resp.geturl())
    except urllib.error.HTTPError as exc:
        if exc.code != 302:
            sys.exit(f"FAIL: POST returned {exc.code}")
        print("POST /accounts/password-reset/ -> 302 (redirect: reset sent)")
        print("      Location:", exc.headers.get("Location"))

    # --- 3. the "check your email" page ---------------------------------
    req = urllib.request.Request(
        BASE + "/accounts/password-reset/sent/", headers={"User-Agent": UA}
    )
    with opener.open(req, timeout=30) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    ok = "If an account exists" in body
    print("GET  /accounts/password-reset/sent/ ->", resp.status,
          "| privacy wording present:", ok)
    if not ok:
        sys.exit("FAIL: sent page missing the privacy wording")
    print("\nReset requested for", email, "- the link is in that inbox.")


if __name__ == "__main__":
    main()