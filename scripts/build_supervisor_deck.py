"""Build the CBODS supervisor status-update deck as a .pptx file.

Run:  venv\\Scripts\\python.exe scripts\\build_supervisor_deck.py
Output: CBODS_Supervisor_Update.pptx (16:9, 9 slides)

Content mirrors docs outline: every claim is verifiable from the codebase
or the deployed demo (see the repo README and docs/ER_DIAGRAM.md).
"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUT = Path(__file__).resolve().parent.parent / "CBODS_Supervisor_Update.pptx"

DARK = RGBColor(0x1F, 0x29, 0x37)
RED = RGBColor(0xB3, 0x2D, 0x2E)
GRAY = RGBColor(0x4B, 0x55, 0x63)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# --------------------------------------------------------------------------
# Slide content: (title, [bullets]).  A bullet starting with two spaces is a
# level-2 sub-bullet.
# --------------------------------------------------------------------------
SLIDES = [
    (
        "CBODS — Centralised Blood & Organ Donation System",
        [
            "Project status update — working MVP (Django 5 web application)",
            "Final-year project · September 2026",
        ],
    ),
    (
        "Purpose & Goal",
        [
            "One platform connecting the full donation chain: donors → hospitals → patients → administrators",
            "What the system delivers:",
            "  Verified donor registry — identity-checked, screened donors only",
            "  Traceable blood inventory — collection → storage → issue, per hospital",
            "  Structured patient blood requests with urgency handling",
            "  Organ donation requests between donors and hospitals",
            "  Full audit trail for accountability on every key action",
            "Stated explicitly in the app: not for clinical use — a demonstration/prototype system",
        ],
    ),
    (
        "Who Uses It (Roles & Modules)",
        [
            "Five account types: Admin, Hospital organisation, Hospital staff, Donor, Patient",
            "Eight modules: accounts, hospitals, donors, inventory, blood requests, organs, notifications, audit",
            "Seeded demo dataset covers every role (admin, 2 hospitals with staff, 25 donors, 3 patients)",
            "Every screen is role-specific — users only see what their role permits",
        ],
    ),
    (
        "Working Today: Donor Registration & Screening",
        [
            "Self-service registration with government-ID upload (≤5 MB; JPG/PNG/PDF)",
            "Admin approval queue: ID reviewed before a donor becomes visible; approve / reject-with-reason",
            "Rejected donors can correct details and resubmit; approved donors can edit their own profile",
            "Donor search for hospitals: approved + available donors only; filter by blood group, city, organ type",
            "Two-stage eligibility screening:",
            "  Stage 1 — age 18–60, weight ≥ 50 kg, ≥ 90 days since last donation (computed automatically)",
            "  Stage 2 — hemoglobin and blood pressure checks recorded by hospital staff",
            "  Outcomes: Eligible / Temporarily deferred / Ineligible, with reasons saved and notified",
        ],
    ),
    (
        "Working Today: Blood Supply & Patient Requests",
        [
            "Staff-recorded donations create blood bags (450 ml standard); live stock per hospital & blood group",
            "Stock safeguards: 35-day expiry handling, low-stock and near-expiry warnings",
            "Patients: choose a hospital, see live availability before requesting, set urgency (Routine/Urgent/Emergency)",
            "Hospitals: accept / reject (reason required) / fulfil requests; reserved bags are locked against double-issue",
            "When stock runs short: ranked compatible-donor suggestions; emergency requests broadcast to compatible donors in the city",
            "Full blood-compatibility engine covering all 8 blood groups, offering alternatives on denial",
        ],
    ),
    (
        "Working Today: Organs, Hospitals & Oversight",
        [
            "Organ donation: approved donors submit requests (kidney, liver, heart, lung, cornea, pancreas, skin); hospitals review → approve/reject; donors track live status",
            "Hospitals: online registration, admin approval, self-managed staff accounts; admins can hide/show hospitals",
            "Admin dashboard: live charts (donors by status, stock by group/hospital, requests by status/urgency) plus approval queues",
            "Audit log: who/what/when recorded for every key action — filterable and searchable",
            "CSV exports: donors, donations, requests, blood bags, and the audit trail",
        ],
    ),
    (
        "Architecture & Approach",
        [
            "Django 5 web app, server-rendered pages (Bootstrap), SQLite database",
            "Modular: eight small apps, each following model → service → view structure",
            "Design principles:",
            "  Nothing computed is stored — stock levels, donor age, next-eligible date are always derived from records",
            "  Business rules live in a service layer, not scattered through pages",
            "  Race-safe stock operations — reserve/issue run inside database transactions",
            "  Privacy enforced per role, including ID documents visible to admins only",
            "All business thresholds (age limits, intervals, screening values) configurable in one settings file",
        ],
    ),
    (
        "Quality & Testing",
        [
            "123 automated tests, all passing (verified locally)",
            "Coverage includes: eligibility boundaries, blood-compatibility tree, double-issue safety, privacy partitions, ID-document security",
            "A full end-to-end test drives the whole story over HTTP: register → approve → screen → donate → request → issue → emergency broadcast → organ request → audit trail",
            "Note for docs cleanup: README still states 45 tests — figure is out of date",
        ],
    ),
    (
        "Current Deployment & Known Gaps",
        [
            "Deployed and live on PythonAnywhere; local development via manage.py runserver",
            "Known gaps (all verified in code/config):",
            "  Emails print to the server log only — no real email delivery yet (resets, notifications)",
            "  SQLite database — fine for demo scale, not multi-user production",
            "  Screening thresholds are assumed values — need clinical confirmation",
            "  Secret key must be set via environment variable for any shared deployment (dev fallback is public in history)",
            "  No automated CI pipeline yet",
            "Recommended next steps:",
            "  Connect a real email service",
            "  Clinically validate screening thresholds",
            "  Add CI (run tests on every commit)",
            "  Plan production database migration when scaling",
        ],
    ),
]


def _set_run(run, size, color, bold=False, italic=False):
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = "Calibri"


def build():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for idx, (title, bullets) in enumerate(SLIDES):
        if idx == 0:
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            # Red accent band along the top of the title slide.
            band = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, Inches(0.18)
            )
            band.fill.solid()
            band.fill.fore_color.rgb = RED
            band.line.fill.background()

            t = slide.shapes.title
            t.left, t.top, t.width, t.height = Inches(1.0), Inches(2.2), Inches(11.3), Inches(1.6)
            t.text_frame.word_wrap = True
            _set_run(t.text_frame.paragraphs[0].add_run(), 40, DARK, bold=True)
            t.text_frame.paragraphs[0].runs[0].text = title

            sub = slide.placeholders[1]
            sub.left, sub.top, sub.width, sub.height = Inches(1.0), Inches(3.9), Inches(11.3), Inches(1.2)
            for i, line in enumerate(bullets):
                p = sub.text_frame.paragraphs[0] if i == 0 else sub.text_frame.add_paragraph()
                p.alignment = PP_ALIGN.LEFT
                p.space_after = Pt(4)
                _set_run(p.add_run(), 18, GRAY, italic=True)
                p.runs[0].text = line
            continue

        slide = prs.slides.add_slide(prs.slide_layouts[1])
        tp = slide.shapes.title.text_frame.paragraphs[0]
        run = tp.add_run()
        _set_run(run, 30, DARK, bold=True)
        run.text = title

        # Thin red rule under the title.
        rule = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.42), Inches(1.6), Inches(0.07)
        )
        rule.fill.solid()
        rule.fill.fore_color.rgb = RED
        rule.line.fill.background()

        body = slide.placeholders[1]
        tf = body.text_frame
        tf.word_wrap = True
        for i, line in enumerate(bullets):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            level = 1 if line.startswith("  ") else 0
            text = line[2:] if level else line
            p.level = level
            p.space_after = Pt(8)
            p.space_before = Pt(2)
            _set_run(p.add_run(), 16 if level == 0 else 15, DARK if level == 0 else GRAY)
            p.runs[0].text = text

        # Footer: project name left, slide number right.
        footer_left = slide.shapes.add_textbox(
            Inches(0.6), Inches(7.05), Inches(8.0), Inches(0.35)
        )
        _set_run(footer_left.text_frame.paragraphs[0].add_run(), 10, GRAY, italic=True)
        footer_left.text_frame.paragraphs[0].runs[0].text = (
            "CBODS — Centralised Blood & Organ Donation System"
        )

        footer_right = slide.shapes.add_textbox(
            Inches(11.9), Inches(7.05), Inches(0.9), Inches(0.35)
        )
        fp = footer_right.text_frame.paragraphs[0]
        fp.alignment = PP_ALIGN.RIGHT
        _set_run(fp.add_run(), 10, GRAY)
        fp.runs[0].text = str(idx)

    prs.save(OUT)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"Saved {path} ({path.stat().st_size:,} bytes)")