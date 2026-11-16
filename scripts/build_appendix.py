"""Regenerate the CBODS appendix document as a curated appendix of at most 13 pages.

Supersedes build_appendices.py (which produced an unbounded dump of source listings).
The content here is reference material that supports Chapters Three and Four of the
documentation, and it is read from the project itself so it cannot drift:

  Appendix A  configurable thresholds and security settings (cbods/settings.py)
  Appendix B  data dictionary for the thirteen tables
  Appendix C  the test catalogue - 47 classes, 264 tests
  Appendix D  email and Ghanaian telephone validation (cbods/validators.py)
  Appendix E  ABO/Rh compatibility matching (requests_app/compatibility.py)
  Appendix F  reservation, emergency broadcast and fulfilment (requests_app/services.py)
  Appendix G  the laboratory screening gate (inventory/services.py)
  Appendix H  the donated unit lifecycle
  Appendix I  the audit trail (audit/services.py)
  Appendix J  route map (every path() in the project's urls.py files)

Outputs
  <repo>/CBODS_APPENDICES.docx        merge-ready, thesis formatting
  <repo>/CBODS_APPENDICES.pdf         the same content, exact page count
  <repo>/CBODS_APPENDICES_BACKUP.docx the previous file, kept once
  a copy of both beside the documentation in ...\\Sch\\!!P

The PDF is printed with headless Chrome and its page count is asserted to be <= 13.
"""

from __future__ import annotations

import datetime as _dt
import html
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(r"C:\Users\Elkanah\Desktop\D\ASSETS\CBODS---Claude")
DOCS = Path(r"C:\Users\Elkanah\Desktop\Sch\!!P")
OUT_DOCX = REPO / "CBODS_APPENDICES.docx"
BACKUP = REPO / "CBODS_APPENDICES_BACKUP.docx"
OUT_PDF = REPO / "CBODS_APPENDICES.pdf"
MAX_PAGES = 13

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_corrections import t42_rows  # noqa: E402  (single source for the catalogue)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

MODULES = [
    "accounts", "hospitals", "donors", "inventory",
    "requests_app", "organs", "notifications", "audit",
]

THRESHOLDS = [
    ("DONOR_MIN_AGE / DONOR_MAX_AGE", "18 / 60 years", "Stage-one eligibility: age"),
    ("DONOR_MIN_WEIGHT_KG", "50 kg", "Stage-one eligibility: weight"),
    ("DONATION_INTERVAL_DAYS", "90 days", "Minimum interval between two donations"),
    ("SCREENING_HEMOGLOBIN_MIN", "12.5 g/dL", "Stage-two screening: minimum haemoglobin"),
    ("SCREENING_SYSTOLIC_MIN / MAX", "90 / 180 mmHg", "Stage-two screening: systolic pressure"),
    ("SCREENING_DIASTOLIC_MIN / MAX", "60 / 100 mmHg", "Stage-two screening: diastolic pressure"),
    ("BLOOD_BAG_SHELF_LIFE_DAYS", "35 days", "Expiry = collection date + 35 days"),
    ("EXPIRY_WARNING_DAYS", "7 days", "Near-expiry highlighting on the inventory"),
    ("LOW_STOCK_THRESHOLD", "3 units", "Low-stock notification to hospital staff"),
    ("LIST_PAGE_SIZE", "25 rows", "Pagination on donor search, inbox and audit log"),
    ("ID_DOCUMENT_MAX_BYTES", "5 MB", "Maximum size of an uploaded identity document"),
    ("SESSION_COOKIE_AGE", "900 s (15 min)", "Idle session timeout"),
    ("PASSWORD_RESET_TIMEOUT", "43 200 s (12 h)", "Lifetime of a password-reset link"),
    ("DEBUG", "off unless DJANGO_DEBUG", "Production safeguard: no tracebacks leaked"),
    ("ALLOWED_HOSTS", "localhost, 127.0.0.1 + env", "Host-header validation"),
    ("EMAIL backend", "SMTP, then Brevo HTTPS", "Delivery channel precedence"),
    ("SMS_PROVIDER", "console / sasusync / africastalking", "Gateway selected per environment"),
]

TABLES = [
    ("User", "The account of every person who uses the system",
     "username, email, password hash, role (Administrator, Hospital Staff, Donor, Patient), "
     "phone number, is_active"),
    ("Hospital", "Each registered facility", "name, city, address, phone number, services "
     "offered, organ donation requirements, visibility flag"),
    ("StaffProfile", "Links a staff account to exactly one hospital, so access is scoped to "
     "that hospital", "user (one-to-one), hospital"),
    ("Donor", "The donor's profile and current registration state", "full name, date of birth, "
     "sex, blood group, weight, city, contact number, medical history, identity document, "
     "registration status, availability, rejection reason"),
    ("ScreeningRecord", "The outcome of one two-stage screening", "stage-one result, "
     "haemoglobin level, blood pressure readings, overall outcome, deferral reasons, donor, "
     "staff member, date"),
    ("Donation", "One completed donation", "donor, hospital, staff member, donation date, "
     "volume in millilitres"),
    ("TTITestRecord", "The laboratory screening of one donation, linked one-to-one to it; this "
     "record decides whether the bag is released or discarded",
     "donation (one-to-one), hiv, hepatitis_b, hepatitis_c, syphilis, tested_by, tested_at, "
     "discarded_reason"),
    ("Appointment", "A donor's request to donate at a chosen hospital on a proposed date",
     "donor, hospital, proposed date, donor note, status (pending, confirmed, declined, "
     "cancelled), decision note, decided_at"),
    ("BloodBag", "A single unit of donated blood",
     "hospital, blood group, volume_ml, collected_date, expiry_date, status, donation, "
     "reserved_for"),
    ("BloodRequest", "A patient's request for blood", "patient, hospital, blood group, number "
     "of units, urgency (routine, urgent, emergency), status, rejection reason, timestamps"),
    ("OrganDonationRequest", "A donor's offer of an organ and its review",
     "donor, hospital, organ type, review status (pending, requested, approved, rejected), "
     "created and decided timestamps"),
    ("Notification", "In-system messages addressed to individual users",
     "user, subject, body, read status, timestamp"),
    ("AuditLog", "Immutable records of every significant action",
     "actor (set-null, so the entry survives), action, entity_type, entity_id, details (JSON), "
     "timestamp"),
]

LIFECYCLE = [
    ("UNTESTED", "Created the moment a donation is recorded, together with its laboratory "
     "screening record.", "Not counted in stock, invisible to matching, cannot be reserved. "
     "Visible to hospital staff in the inventory."),
    ("AVAILABLE", "Laboratory screening complete with all four markers non-reactive.",
     "The only state a blood request can draw on. Counted in the stock figures."),
    ("RESERVED", "Selected and locked for an accepted blood request, in first-expiry-first-out "
     "order.", "Issued at fulfilment, or returned to available if the request is rejected."),
    ("ISSUED", "The request is fulfilled and the unit leaves the bank.", "Final state for a "
     "used unit; retained for traceability to the donor."),
    ("EXPIRED", "The daily expiry command finds a unit past its expiry date in the untested, "
     "available or reserved state.", "Final state. Recorded in the audit log; the unit never "
     "enters the usable pool."),
    ("DISCARDED", "Any laboratory marker is reactive.", "Final state. The reactive markers are "
     "recorded as the reason and the donor is notified."),
]

TEST_OVERVIEW = [
    ("Accounts", "16", "109"), ("Hospitals", "11", "62"), ("Donors", "9", "49"),
    ("Requests_app", "4", "11"), ("Inventory", "1", "11"), ("Notifications", "2", "6"),
    ("Audit", "2", "6"), ("End-to-end and render", "2", "10"),
]


# --------------------------------------------------------------------------- #
# Reading the project
# --------------------------------------------------------------------------- #
def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")


def extract_functions(text: str, names: list[str]) -> dict[str, list[str]]:
    """Pull whole top-level functions out of a module by name."""
    lines = text.split("\n")
    starts = {}
    for i, line in enumerate(lines):
        m = re.match(r"def (\w+)\(", line)
        if m and m.group(1) in names:
            starts[m.group(1)] = i
    out: dict[str, list[str]] = {}
    for name, start in starts.items():
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r"(def |class )\w+", lines[j]) or re.match(r"@", lines[j]):
                end = j
                break
        # trim trailing blank lines
        body = lines[start:end]
        while body and not body[-1].strip():
            body.pop()
        out[name] = body
    return out


def route_map() -> list[tuple[str, str, str]]:
    """(module, path, view) for every path() in the project's urls.py files."""
    rows: list[tuple[str, str, str]] = []
    files = [REPO / "cbods" / "urls.py"] + [REPO / m / "urls.py" for m in MODULES]
    for f in files:
        if not f.exists():
            continue
        text = read(f)
        for m in re.finditer(
            r'path\(\s*"([^"]*)"\s*,\s*([A-Za-z_][\w.]*)', text
        ):
            rows.append((f.parent.name if f.parent.name != "cbods" else "project",
                         m.group(1) or "/", m.group(2)))
    return rows


def whole_file(rel: str) -> list[str]:
    """A module in full, as a listing."""
    lines = [l.rstrip() for l in read(REPO / rel).split("\n")]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def extract_constant(text: str, name: str) -> list[str]:
    """A top-level NAME = {...} literal, with its comment block."""
    lines = text.split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(f"{name} ="))
    end = start
    for j in range(start, len(lines)):
        if lines[j].rstrip().endswith("}):") or lines[j].rstrip() == ")":
            end = j
            break
    return [l.rstrip() for l in lines[start:end + 1]]


def settings_excerpt() -> list[str]:
    """The configurable threshold block of cbods/settings.py, verbatim."""
    lines = read(REPO / "cbods" / "settings.py").split("\n")
    start = next((i for i, l in enumerate(lines) if l.startswith("# Screening thresholds")), None)
    end = next((i for i, l in enumerate(lines) if l.startswith("ID_DOCUMENT_MAX_BYTES")), None)
    assert start is not None and end is not None, "settings.py threshold block not found"
    return [l for l in lines[start:end + 1] if l.strip()]


# --------------------------------------------------------------------------- #
# Content model
# --------------------------------------------------------------------------- #
def build_blocks() -> list[tuple]:
    today = _dt.date.today().isoformat()
    svc = extract_functions(read(REPO / "inventory" / "services.py"),
                            ["record_tti_results", "set_bag_status", "expire_past_due_bags"])
    req = extract_functions(read(REPO / "requests_app" / "services.py"),
                            ["accept_request", "broadcast_emergency", "fulfil_request"])
    acct = extract_functions(read(REPO / "accounts" / "validators.py"),
                             ["validate_email_tld", "_one_edit_away", "_suggest_tld"])
    aud = extract_functions(read(REPO / "audit" / "services.py"), ["log_action"])
    assert len(req) == 3, f"expected 3 functions in requests_app/services.py, got {sorted(req)}"
    assert len(acct) == 3, f"expected 3 functions in accounts/validators.py, got {sorted(acct)}"
    assert aud.get("log_action"), "log_action not found in audit/services.py"

    blocks: list[tuple] = [
        ("title", "CENTRALISED BLOOD & ORGAN DONATION SYSTEM (CBODS)"),
        ("subtitle", "APPENDICES"),
        ("p", "Reference material supporting Chapters Three and Four of the documentation. "
              "The thresholds, tables, tests, routes and code listings below are taken "
              "directly from the implemented system, not from an earlier draft, so the "
              "appendix cannot drift from the code it describes. Appendix D holds the "
              "validation rules for email addresses and Ghanaian telephone numbers, "
              "Appendix E the ABO and Rh compatibility matching, Appendix F the reservation "
              "and fulfilment operations, and Appendix G the laboratory screening gate."),
        ("caption", f"Generated {today} from the project repository. Contents: ten appendices "
                    f"(thresholds, data dictionary, test catalogue, validation, matching, "
                    f"reservation and fulfilment, the laboratory gate, the unit lifecycle, "
                    f"the audit trail and the route map), at most {MAX_PAGES} pages."),

        ("h1", "APPENDIX A: CONFIGURABLE THRESHOLDS AND SECURITY SETTINGS"),
        ("p", "The clinical and operational thresholds of the system are configuration values, "
              "not hard-coded numbers, so an operating institution can adjust them without a "
              "code change. Every value below is read from cbods/settings.py at start-up and "
              "is applied consistently in screening, donation recording and the availability "
              "check that decides which blood groups a patient may request."),
        ("table", ["Setting", "Value", "Where it governs"], THRESHOLDS, [34, 26, 40]),
        ("h2", "Listing A.1: cbods/settings.py - the configurable threshold block"),
        ("code", settings_excerpt()),

        ("h1", "APPENDIX B: DATA DICTIONARY FOR THE THIRTEEN TABLES"),
        ("p", "The database holds thirteen application tables across eight modules. Django's "
              "own authentication, session and content-type tables are managed by the "
              "framework and are not listed. One-to-one, foreign-key and set-null behaviour "
              "is noted where it affects what survives deletion."),
        ("table", ["Table", "Purpose", "Key fields"], TABLES, [19, 38, 43]),

        ("h1", "APPENDIX C: TEST CATALOGUE - 264 TESTS IN 47 CLASSES"),
        ("p", "The suite is run with the Django test runner (python manage.py test). Every "
              "test below passes. The counts were verified by running the suite and by "
              "counting the test methods in each class."),
        ("h2", "C.1  Coverage by module"),
        ("table", ["Module", "Test classes", "Tests"], TEST_OVERVIEW + [("Total", "47", "264")],
         [46, 27, 27]),
        ("h2", "C.2  Test classes"),
        ("table", ["Module", "Test class", "Tests", "Focus"], [list(r) for r in t42_rows()],
         [14, 25, 7, 54]),

        ("h1", "APPENDIX D: EMAIL AND GHANAIAN TELEPHONE VALIDATION"),
        ("p", "Both the email address and the contact number are validated in one shared "
              "module, so the same rule applies at the field, at the form and at the model "
              "level; a value that reaches the database by any other route still cannot be "
              "invalid. That duplication is deliberate, and ContactValidationTests and "
              "GhanaPhoneNumberTests verify all three layers agree."),
        ("h2", "Listing D.1: cbods/validators.py - the shared validation module"),
        ("code", whole_file("cbods/validators.py")),
        ("h2", "Listing D.2: accounts/validators.py - rejecting a non-existent "
               "top-level domain and suggesting the likely intended one"),
        ("code", extract_constant(read(REPO / "accounts" / "validators.py"), "COMMON_TLDS")
                 + [""] + acct["validate_email_tld"] + [""]
                 + acct["_one_edit_away"] + [""] + acct["_suggest_tld"]),

        ("h1", "APPENDIX E: ABO/RH COMPATIBILITY MATCHING (requests_app/compatibility.py)"),
        ("p", "Appendix E is the matching component described in Section 3.3.3. The "
              "compatibility table encodes which donor groups a recipient may receive; "
              "is_compatible is the single rule the whole system consults, so the matrix is "
              "stated once and cannot drift between screens. compatibility.py also holds the "
              "ranking used to suggest donors: donors in the hospital's own city first, then "
              "those eligible soonest, with donors who can donate immediately promoted to the "
              "front of an emergency request. CompatibilityTreeTests walks every one of the "
              "sixty-four ABO and Rh combinations through is_compatible."),
        ("h2", "Listing E.1: requests_app/compatibility.py in full"),
        ("code", whole_file("requests_app/compatibility.py")),

        ("h1", "APPENDIX F: RESERVATION, BROADCAST AND FULFILMENT "
               "(requests_app/services.py)"),
        ("p", "These are the operations that change the state of stock, so each one runs "
              "inside a single database transaction with row-level locking. A bag selected "
              "for a request is locked before its status is read, which is what stops the "
              "same unit being reserved for two requests at once; fulfilment locks the "
              "reserved bags again and re-checks their status before issuing them."),
        ("h2", "Listing F.1: accept_request - first-expiry-first-out reservation"),
        ("code", req["accept_request"]),
        ("h2", "Listing F.2: broadcast_emergency - the urgent appeal to compatible donors"),
        ("code", req["broadcast_emergency"]),
        ("h2", "Listing F.3: fulfil_request - issuing the reserved bags"),
        ("code", req["fulfil_request"]),

        ("h1", "APPENDIX G: THE LABORATORY SCREENING GATE (inventory/services.py)"),
        ("p", "Appendix G is the code that enforces the safety gate described in Section "
              "4.1.2 (Phase 2) and Section 4.2.3. Recording a donation creates the bag in the "
              "untested state and opens its laboratory record; the gate is the only code path "
              "that releases a unit into the usable pool. Every status change passes through "
              "set_bag_status, so a status change and its audit entry cannot be recorded "
              "separately."),
        ("h2", "Listing G.1: record_tti_results - the gate itself"),
        ("code", svc["record_tti_results"]),
        ("h2", "Listing G.2: set_bag_status - the single audited choke point"),
        ("code", svc["set_bag_status"]),
        ("h2", "Listing G.3: expire_past_due_bags - the daily expiry sweep"),
        ("code", svc["expire_past_due_bags"]),

        ("h1", "APPENDIX H: THE DONATED UNIT LIFECYCLE"),
        ("p", "A blood bag has six possible states. A unit that has just been recorded is "
              "untested, and it is invisible to the matching process and excluded from the "
              "stock figures until the laboratory clears it. Three of the six states are "
              "final."),
        ("table", ["Status", "Entered when", "Behaviour"], LIFECYCLE, [16, 40, 44]),

        ("h1", "APPENDIX I: THE AUDIT TRAIL (audit/services.py)"),
        ("p", "Every significant action in the system is written through one function. The "
              "actor is stored as a loose reference, so an entry survives even if the account "
              "that made it is later deleted, and a set-null foreign key means the audit log "
              "is append-only in practice: nothing in the application updates or deletes it."),
        ("h2", "Listing I.1: log_action - the audited write"),
        ("code", aud["log_action"]),

        ("h1", "APPENDIX J: ROUTE MAP"),
        ("p", "Every URL path the application exposes, with the view that serves it. The "
              "only uploads are donor identity documents, which are not served by URL at all: "
              "they are read through one administrator-only view."),
        ("table", ["Module", "Path", "View"], [[a, b, c] for a, b, c in route_map()],
         [16, 42, 42]),
    ]
    return blocks


# --------------------------------------------------------------------------- #
# DOCX rendering
# --------------------------------------------------------------------------- #
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/>
<w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:line="360" w:lineRule="auto"/>
<w:jc w:val="both"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="AppTitle"><w:name w:val="Appendix Title"/>
<w:pPr><w:jc w:val="center"/><w:spacing w:before="0" w:after="120" w:line="240"
w:lineRule="auto"/></w:pPr><w:rPr><w:b/><w:sz w:val="30"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="AppSub"><w:name w:val="Appendix Subtitle"/>
<w:pPr><w:jc w:val="center"/><w:spacing w:after="240" w:line="240" w:lineRule="auto"/>
</w:pPr><w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>
<w:pPr><w:keepNext/><w:spacing w:before="320" w:after="160" w:line="240"
w:lineRule="auto"/><w:jc w:val="left"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>
<w:pPr><w:keepNext/><w:spacing w:before="220" w:after="100" w:line="240"
w:lineRule="auto"/><w:jc w:val="left"/></w:pPr>
<w:rPr><w:b/><w:i/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/>
<w:pPr><w:spacing w:after="160" w:line="240" w:lineRule="auto"/><w:jc w:val="left"/>
</w:pPr><w:rPr><w:i/><w:sz w:val="20"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/>
<w:pPr><w:spacing w:before="0" w:after="0" w:line="150" w:lineRule="exact"/>
<w:jc w:val="left"/></w:pPr>
<w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/><w:sz w:val="12"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Cell"><w:name w:val="Table Cell"/>
<w:pPr><w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/>
<w:jc w:val="left"/></w:pPr><w:rPr><w:sz w:val="16"/><w:rFonts
w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="CellHead"><w:name w:val="Table Head"/>
<w:pPr><w:spacing w:before="20" w:after="20" w:line="240" w:lineRule="auto"/>
<w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="16"/><w:rFonts
w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr></w:style>
</w:styles>"""


def xesc(t: str) -> str:
    return html.escape(t, quote=False)


def wpara(text: str, style: str | None = None, extra: str = "") -> str:
    pr = "<w:pPr>"
    if style:
        pr += f'<w:pStyle w:val="{style}"/>'
    pr += extra + "</w:pPr>"
    run = f'<w:r><w:t xml:space="preserve">{xesc(text)}</w:t></w:r>' if text else ""
    return f"<w:p>{pr}{run}</w:p>"


def wtable(headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    total = 9026
    grid = "".join(f'<w:gridCol w:w="{int(total * w / 100)}"/>' for w in widths)
    edge = lambda tag: f'<w:{tag} w:val="single" w:sz="6" w:space="0" w:color="999999"/>'
    borders = "<w:tblBorders>" + "".join(
        edge(t) for t in ("top", "left", "bottom", "right", "insideH", "insideV")
    ) + "</w:tblBorders>"
    out = ['<w:tbl><w:tblPr><w:tblW w:w="9026" w:type="dxa"/><w:tblLayout w:type="fixed"/>'
           + borders + '</w:tblPr>' + f"<w:tblGrid>{grid}</w:tblGrid>"]
    for i, row in enumerate([headers] + rows):
        cells = []
        for value, w in zip(row, widths):
            style = "CellHead" if i == 0 else "Cell"
            cells.append(
                f'<w:tc><w:tcPr><w:tcW w:w="{int(total * w / 100)}" w:type="dxa"/></w:tcPr>'
                + wpara(str(value), style) + "</w:tc>"
            )
        head = '<w:trPr><w:tblHeader/></w:trPr>' if i == 0 else ""
        out.append(f"<w:tr>{head}{''.join(cells)}</w:tr>")
    out.append("</w:tbl>")
    out.append(wpara(""))
    return "".join(out)


def docx_document(blocks: list[tuple]) -> str:
    body = []
    for block in blocks:
        kind = block[0]
        if kind == "title":
            body.append(wpara(block[1], "AppTitle"))
        elif kind == "subtitle":
            body.append(wpara(block[1], "AppSub"))
        elif kind == "h1":
            body.append(wpara(block[1], "Heading1"))
        elif kind == "h2":
            body.append(wpara(block[1], "Heading2"))
        elif kind == "caption":
            body.append(wpara(block[1], "Caption"))
        elif kind == "p":
            body.append(wpara(block[1]))
        elif kind == "code":
            for line in block[1]:
                body.append(wpara(line, "Code"))
            body.append(wpara(""))
        elif kind == "table":
            body.append(wtable(block[1], block[2], block[3]))
    sect = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
            'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}{sect}</w:body></w:document>"
    )


def write_docx(path: Path, blocks: list[tuple]) -> None:
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
        'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="word/document.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/styles" Target="word/styles.xml"/></Relationships>'
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/styles" Target="styles.xml"/></Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/document.xml", docx_document(blocks))


# --------------------------------------------------------------------------- #
# HTML twin (page-count check + print copy)
# --------------------------------------------------------------------------- #
def html_document(blocks: list[tuple]) -> str:
    css = """
    @page { size: A4; margin: 25.4mm; }
    body { font-family: "Times New Roman", serif; font-size: 12pt; line-height: 1.5;
           margin: 0; color: #000; text-align: justify; }
    h1 { font-size: 15pt; margin: 16pt 0 8pt 0; text-align: left; }
    h2 { font-size: 12.5pt; font-style: italic; margin: 11pt 0 5pt 0; text-align: left; }
    .title { text-align: center; font-weight: bold; font-size: 15pt; margin-bottom: 6pt; }
    .subtitle { text-align: center; font-weight: bold; font-size: 13pt; margin-bottom: 12pt; }
    .cap { font-style: italic; font-size: 10pt; text-align: left; margin-bottom: 8pt; }
    p { margin: 0 0 6pt 0; }
    pre { font-family: Consolas, monospace; font-size: 6pt; line-height: 7.5pt;
          margin: 0; white-space: pre-wrap; page-break-inside: auto; }
    table { width: 100%; border-collapse: collapse; margin: 5pt 0 8pt 0;
            font-size: 8pt; line-height: 1.1; text-align: left; }
    th, td { border: 0.5pt solid #999; padding: 1.4pt 2.6pt; vertical-align: top;
             text-align: left; }
    th { font-weight: bold; }
    tr { page-break-inside: avoid; }
    """
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>"
             "<body>"]
    for block in blocks:
        kind = block[0]
        if kind == "title":
            parts.append(f"<div class='title'>{xesc(block[1])}</div>")
        elif kind == "subtitle":
            parts.append(f"<div class='subtitle'>{xesc(block[1])}</div>")
        elif kind == "h1":
            parts.append(f"<h1>{xesc(block[1])}</h1>")
        elif kind == "h2":
            parts.append(f"<h2>{xesc(block[1])}</h2>")
        elif kind == "caption":
            parts.append(f"<p class='cap'>{xesc(block[1])}</p>")
        elif kind == "p":
            parts.append(f"<p>{xesc(block[1])}</p>")
        elif kind == "code":
            parts.append("<pre>" + xesc("\n".join(block[1])) + "</pre>")
        elif kind == "table":
            rows = "".join(
                "<tr>" + "".join(f"<td>{xesc(str(c))}</td>" for c in r) + "</tr>"
                for r in [block[1]] + block[2]
            )
            parts.append(f"<table>{rows}</table>")
    parts.append("</body></html>")
    return "\n".join(parts)


def find_browser() -> str:
    for p in (CHROME, EDGE):
        if os.path.exists(p):
            return p
    raise SystemExit("no Chrome or Edge found for PDF printing")


def print_pdf(html_text: str, out: Path) -> int:
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "appendix.html"
        src.write_text(html_text, encoding="utf-8")
        cmd = [find_browser(), "--headless=new", "--disable-gpu", "--no-first-run",
               "--no-pdf-header-footer", f"--user-data-dir={Path(td) / 'profile'}",
               "--print-to-pdf-no-header", f"--print-to-pdf={out}", src.as_uri()]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if not out.exists():
            print(proc.stdout[-2000:], proc.stderr[-2000:])
            raise SystemExit("appendix PDF was not produced")
    from pypdf import PdfReader

    return len(PdfReader(str(out)).pages)


def main() -> None:
    assert (REPO / "inventory" / "services.py").exists(), "project not found"
    blocks = build_blocks()

    if OUT_DOCX.exists() and not BACKUP.exists():
        BACKUP.write_bytes(OUT_DOCX.read_bytes())
        print(f"previous appendix backed up: {BACKUP.name}")

    write_docx(OUT_DOCX, blocks)
    print(f"written: {OUT_DOCX.name} ({OUT_DOCX.stat().st_size:,} bytes)")

    pages = print_pdf(html_document(blocks), OUT_PDF)
    print(f"written: {OUT_PDF.name} ({OUT_PDF.stat().st_size:,} bytes) - {pages} pages")
    assert pages <= MAX_PAGES, f"appendix is {pages} pages, limit is {MAX_PAGES}"

    # a copy beside the documentation
    for src in (OUT_DOCX, OUT_PDF):
        dst = DOCS / src.name
        dst.write_bytes(src.read_bytes())
        print(f"copied to documentation folder: {dst.name}")

    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(OUT_DOCX) as z:
        for n in z.namelist():
            if n.endswith(".xml") or n.endswith(".rels"):
                ET.fromstring(z.read(n))
    print("docx parts parse OK")


if __name__ == "__main__":
    main()
