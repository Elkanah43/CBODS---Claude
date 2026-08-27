"""Capture screenshots of all CBODS pages for documentation - fresh context per role."""
import os
import time
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Pages grouped by the login needed
PUBLIC_PAGES = [
    ("01-login", "/accounts/login/"),
    ("02-register", "/accounts/register/"),
    ("03-password-reset", "/accounts/password-reset/"),
]

ADMIN_PAGES = [
    ("04-dashboard", "/accounts/dashboard/"),
    ("05-audit-dashboard", "/audit/dashboard/"),
    ("06-audit-log", "/audit/log/"),
    ("07-donors-search", "/donors/search/"),
    ("09-donors-approvals", "/donors/approvals/"),
    ("16-hospitals-approvals", "/hospitals/approvals/"),
    ("17-hospitals-manage", "/hospitals/manage/"),
    ("23-notifications", "/notifications/"),
    ("24-django-admin", "/admin/"),
]

STAFF_PAGES = [
    ("08-donors-screening", "/donors/screening/"),
    ("10-inventory-stock", "/inventory/stock/"),
    ("11-inventory-donate", "/inventory/donate/"),
    ("15-requests-match", "/requests/match/"),
    ("18-hospitals-reports", "/hospitals/reports/"),
    ("19-hospitals-activity", "/hospitals/activity/"),
    ("22-organs-review", "/organs/review/"),
    ("26-hospital-staff", "/hospitals/staff/"),
]

PATIENT_PAGES = [
    ("12-requests-hospitals", "/requests/hospitals/"),
    ("13-requests-mine", "/requests/mine/"),
    ("14-requests-inbox", "/requests/inbox/"),
]

DONOR_PAGES = [
    ("20-organs-new", "/organs/new/"),
    ("21-organs-mine", "/organs/mine/"),
    ("27-donor-profile", "/donors/profile/"),
]


def login_and_capture(p, pages, username, password, role_name):
    """Login and capture pages in a fresh browser context."""
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        device_scale_factor=2,
    )
    page = context.new_page()

    print(f"\n{'='*60}")
    print(f"Capturing {role_name} pages (user: {username})")
    print(f"{'='*60}")

    # Login
    page.goto(BASE_URL + "/accounts/login/", wait_until="networkidle")
    page.wait_for_selector('input[name="username"]', state="visible", timeout=10000)
    time.sleep(0.3)
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    if "/accounts/login/" in page.url:
        print(f"  FAILED to login as {username}!")
        browser.close()
        return 0

    print(f"  Logged in as {username}")

    count = 0
    for name, url_path in pages:
        full_url = BASE_URL + url_path
        print(f"\n  Capturing {name}: {url_path}")

        try:
            page.goto(full_url, wait_until="networkidle", timeout=15000)
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)

            # Check for redirect to login
            if "/accounts/login/" in page.url:
                print(f"    -> Redirected to login (permission denied)")
                continue

            title = page.title()
            screenshot_path = os.path.join(OUTPUT_DIR, f"{name}.png")
            page.screenshot(path=screenshot_path, full_page=True)
            size_kb = os.path.getsize(screenshot_path) / 1024
            print(f"    -> Saved: {name}.png ({size_kb:.0f}KB) - {title}")
            count += 1

        except Exception as e:
            print(f"    -> ERROR: {e}")

    context.close()
    browser.close()
    return count


def capture_pages():
    with sync_playwright() as p:
        total = 0

        # Public pages (no auth needed)
        print(f"\n{'='*60}")
        print("Capturing public pages (no auth)")
        print(f"{'='*60}")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=2,
        )
        page = context.new_page()
        for name, url_path in PUBLIC_PAGES:
            full_url = BASE_URL + url_path
            print(f"\n  Capturing {name}: {url_path}")
            try:
                page.goto(full_url, wait_until="networkidle", timeout=15000)
                page.wait_for_load_state("networkidle")
                time.sleep(0.5)
                title = page.title()
                screenshot_path = os.path.join(OUTPUT_DIR, f"{name}.png")
                page.screenshot(path=screenshot_path, full_page=True)
                size_kb = os.path.getsize(screenshot_path) / 1024
                print(f"    -> Saved: {name}.png ({size_kb:.0f}KB) - {title}")
                total += 1
            except Exception as e:
                print(f"    -> ERROR: {e}")
        context.close()
        browser.close()

        # Auth pages - fresh context per role
        total += login_and_capture(p, ADMIN_PAGES, "demo_admin", "demo12345", "ADMIN")
        total += login_and_capture(p, STAFF_PAGES, "demo_staff1", "demo12345", "HOSPITAL_STAFF")
        total += login_and_capture(p, PATIENT_PAGES, "demo_patient1", "demo12345", "PATIENT")
        total += login_and_capture(p, DONOR_PAGES, "demo_donor1", "demo12345", "DONOR")

        print(f"\n{'='*60}")
        print(f"DONE! {total} screenshots saved to: {OUTPUT_DIR}")
        print(f"{'='*60}")


if __name__ == "__main__":
    capture_pages()
