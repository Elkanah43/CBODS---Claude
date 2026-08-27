# CBODS Screenshots

Screenshots captured from the live Django development server for documentation purposes.

**Captured:** August 27, 2026  
**Resolution:** 2560×1600 (2x retina)  
**Viewport:** 1280×800

## Public Pages (No Authentication)

| File | Page | URL |
|------|------|-----|
| `01-login.png` | Login page | `/accounts/login/` |
| `02-register.png` | Registration page | `/accounts/register/` |
| `03-password-reset.png` | Password reset request | `/accounts/password-reset/` |

## Admin Pages (demo_admin)

| File | Page | URL |
|------|------|-----|
| `04-dashboard.png` | System dashboard | `/accounts/dashboard/` |
| `05-audit-dashboard.png` | Admin analytics dashboard with charts | `/audit/dashboard/` |
| `06-audit-log.png` | Audit trail | `/audit/log/` |
| `07-donors-search.png` | Available donors search | `/donors/search/` |
| `09-donors-approvals.png` | Donor registration approvals | `/donors/approvals/` |
| `16-hospitals-approvals.png` | Hospital registration approvals | `/hospitals/approvals/` |
| `17-hospitals-manage.png` | Hospital management list | `/hospitals/manage/` |
| `23-notifications.png` | Notification inbox | `/notifications/` |
| `24-django-admin.png` | Django admin panel | `/admin/` |

## Hospital Staff Pages (demo_staff1)

| File | Page | URL |
|------|------|-----|
| `08-donors-screening.png` | Donor health screening | `/donors/screening/` |
| `10-inventory-stock.png` | Blood inventory stock levels | `/inventory/stock/` |
| `11-inventory-donate.png` | Record a blood donation | `/inventory/donate/` |
| `15-requests-match.png` | Blood compatibility check | `/requests/match/` |
| `18-hospitals-reports.png` | Hospital reports | `/hospitals/reports/` |
| `19-hospitals-activity.png` | Hospital activity log | `/hospitals/activity/` |
| `22-organs-review.png` | Organ request review queue | `/organs/review/` |

## Patient Pages (demo_patient1)

| File | Page | URL |
|------|------|-----|
| `12-requests-hospitals.png` | Hospital directory for requests | `/requests/hospitals/` |
| `13-requests-mine.png` | My blood requests | `/requests/mine/` |

## Donor Pages (demo_donor1)

| File | Page | URL |
|------|------|-----|
| `20-organs-new.png` | New organ donation request | `/organs/new/` |
| `21-organs-mine.png` | My organ donation requests | `/organs/mine/` |
| `27-donor-profile.png` | Donor profile page | `/donors/profile/` |

## Pages Not Captured (Permission Restrictions)

These pages require specific role assignments that the demo accounts don't have:

| URL | Required Role | Reason |
|-----|--------------|--------|
| `/requests/inbox/` | PATIENT | Requires patient-to-hospital relationship |
| `/hospitals/staff/` | HOSPITAL | Requires hospital account (not staff) |

## Demo Account Credentials

All demo accounts use password: `demo12345`

| Username | Role |
|----------|------|
| `demo_admin` | Admin (superuser) |
| `demo_staff1` | Hospital Staff |
| `demo_patient1` | Patient |
| `demo_donor1` | Donor |
