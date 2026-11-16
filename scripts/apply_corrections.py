"""Apply the three correction sets into CBODS_NEW V7.2.docx, in place.

Edits performed (deduplicated across the three sets):
  1. Test count: 110/27 -> 264/47 in five sentences (abstract, 4.1.3, 4.3,
     two Chapter Five passages).
  2. Table 4.2 replaced with the verified 47-class table (264 tests, totals
     row), reusing the existing table style.
  3. Table 4.3 (evaluation criteria) rows updated with TTI/reset evidence;
     its caption 4.2 -> 4.3 and the paragraph above it unchanged (already
     cross-references 4.3).
  4. Seven test-category paragraphs in 4.1.3: "four categories" -> seven,
     one sentence change, three new category paragraphs inserted.
  5. TTI gate: Donation recording + new Laboratory screening requirement,
     Inventory management, matching/diagram clauses, audit trail, chapter
     summaries, Phase 2/3/4, 4.2.2 chain, 4.2.4 consistency.
  6. Data design: eleven -> thirteen tables, BloodBag statuses, new TTI +
     Appointment table sentences, design-decision sentence.
  7. "one day" -> "twelve hours"; "4.2.3 Performance Evaluation" -> 4.2.4.
  8. Appointments: new requirement in 3.2.3, new feature entry (Figure 4.10)
     at the end of Key Features, List of Figures line, phase + test sentences.

A timestamped backup of the original file is written next to it first.
New paragraphs reuse the ListParagraph/numbering style of the requirement
paragraphs so the applied text matches the document's own formatting.
"""
from __future__ import annotations

import html
import re
import shutil
import zipfile
from pathlib import Path

SRC = Path(r"C:\Users\Elkanah\Desktop\Sch\!!P\CBODS_NEW V7.2.docx")
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# --------------------------------------------------------------------------- #
# XML helpers
# --------------------------------------------------------------------------- #
def esc(t: str) -> str:
    return html.escape(t, quote=False)


BODY_PPR = (
    "<w:pPr><w:spacing w:line=\"360\" w:lineRule=\"auto\"/>"
    "<w:jc w:val=\"both\"/><w:rPr><w:rFonts w:ascii=\"Times New Roman\" "
    "w:hAnsi=\"Times New Roman\"/></w:rPr></w:pPr>"
)
LIST_PPR = (
    "<w:pPr><w:pStyle w:val=\"ListParagraph\"/>"
    "<w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"4\"/></w:numPr>"
    "<w:spacing w:line=\"360\" w:lineRule=\"auto\"/>"
    "<w:jc w:val=\"both\"/></w:pPr>"
)


def make_para(text: str, *, bold_prefix: str | None = None, style: str = "body") -> str:
    """A paragraph in the document's own body formatting."""
    ppr = LIST_PPR if style == "list" else BODY_PPR
    runs = ""
    if bold_prefix:
        runs += f'<w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t xml:space="preserve">{esc(bold_prefix)}</w:t></w:r>'
    runs += f'<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr><w:t xml:space="preserve">{esc(text)}</w:t></w:r>'
    return f"<w:p>{ppr}{runs}</w:p>"


def para_text(p_xml: str) -> str:
    # strict: <w:t> or <w:t xmlns...>, so <w:tab/>, <w:tc>, <w:tcPr> don't match
    return html.unescape("".join(re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p_xml, re.S)))


def is_field_para(p_xml: str) -> bool:
    """True for TOC / List-of-Figures field paragraphs: their visible text
    duplicates body text, so edits must never target them."""
    return (
        "instrText" in p_xml
        or "PAGEREF" in p_xml
        or "fldSimple" in p_xml
        or 'w:pStyle w:val="TOC' in p_xml
        or "<w:tabs>" in p_xml
    )


def iter_paragraphs(xml: str):
    """Yield (start, end, xml) for every paragraph, nesting-aware (w:p cannot nest)."""
    for m in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        yield m.start(), m.end(), m.group(0)


def replace_para_text(p_xml: str, old: str, new: str) -> str:
    """Replace text spanning runs: rebuild the paragraph with a single run,
    preserving the paragraph properties and any bold lead-in run."""
    m = re.search(r"<w:pPr>.*?</w:pPr>", p_xml, re.S)
    ppr = m.group(0) if m else ""
    bold_lead = ""
    lead = re.search(r"<w:r(?: [^>]*)?><w:rPr><w:b/>.*?</w:rPr>.*?</w:r>", p_xml, re.S)
    if lead:
        lead_txt = para_text(lead.group(0))
        if old.startswith(lead_txt):
            bold_lead = lead.group(0)
            old = old[len(lead_txt):]
            # strip bold lead also from new
    t = para_text(p_xml)
    assert old in t, f"missing text: {old[:60]}"
    t = t.replace(old, new, 1)
    body_run = (
        '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr>'
        f'<w:t xml:space="preserve">{esc(t)}</w:t></w:r>'
    )
    return re.sub(r"<w:p[ >].*?</w:p>", lambda _: p_xml[: len(p_xml) * 0] + "<w:p>" + ppr + bold_lead + body_run + "</w:p>", p_xml, count=1, flags=re.S)


def rebuild_para(p_xml: str, full_new_text: str, *, bold_prefix: str | None = None) -> str:
    m = re.search(r"<w:pPr>.*?</w:pPr>", p_xml, re.S)
    ppr = m.group(0) if m else BODY_PPR
    runs = ""
    if bold_prefix:
        runs += f'<w:r><w:rPr><w:b/><w:bCs/></w:rPr><w:t xml:space="preserve">{esc(bold_prefix)}</w:t></w:r>'
    runs += (
        '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr>'
        f'<w:t xml:space="preserve">{esc(full_new_text)}</w:t></w:r>'
    )
    return f"<w:p>{ppr}{runs}</w:p>"


# --------------------------------------------------------------------------- #
# Table scanner (nesting-aware)
# --------------------------------------------------------------------------- #
def find_tables(s: str):
    out = []
    i = 0
    while True:
        m = re.search(r"<w:tbl[ >]", s[i:])
        if not m:
            break
        start = i + m.start()
        depth = 0
        j = start
        while True:
            m2 = re.compile(r"<w:tbl[ >]|</w:tbl>").search(s, j)
            tag = m2.group(0)
            j = m2.end()
            if tag == "</w:tbl>":
                depth -= 1
                if depth == 0:
                    out.append((start, j))
                    break
            else:
                depth += 1
        i = j
    return out


def find_rows(table_xml: str) -> list[tuple[int, int]]:
    """Spans of the TOP-LEVEL rows of a table. Tracks <w:tbl> depth as well as
    <w:tr> depth, so rows belonging to a nested table are skipped."""
    out = []
    pat = re.compile(r"<w:tbl[ >]|</w:tbl>|<w:tr[ >]|</w:tr>")
    tbl_depth = 0
    tr_depth = 0
    row_start = None
    for m in pat.finditer(table_xml):
        tag = m.group(0)
        if tag.startswith("<w:tbl"):
            tbl_depth += 1
        elif tag == "</w:tbl>":
            tbl_depth -= 1
        elif tag.startswith("<w:tr"):
            tr_depth += 1
            if tbl_depth == 1 and tr_depth == 1:
                row_start = m.start()
        else:  # </w:tr>
            if tbl_depth == 1 and tr_depth == 1 and row_start is not None:
                out.append((row_start, m.end()))
                row_start = None
            tr_depth -= 1
    return out


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #
def t42_rows():
    """(module, class, n, focus) - the verified 47 classes, 264 tests."""
    return [
        ("Accounts", "PrivacyPartitionTests", "6", "Role gates and per-hospital data isolation"),
        ("Accounts", "DuplicateEmailRegistrationTests", "4", "Duplicate email rejected, case-insensitively; address freed by a deactivated account"),
        ("Accounts", "WelcomeNotificationTests", "5", "Welcome email and SMS on registration; a failed send never breaks sign-up"),
        ("Accounts", "LoginUsernamePersistenceTests", "6", "Submitted username kept after a failed login and carried into the reset form, safely escaped"),
        ("Accounts", "ForgotPasswordGateTests", "7", "Reset link unlocked only after a failed sign-in attempt; the unlock is session-scoped"),
        ("Accounts", "PasswordResetFlowTests", "8", "Token-link reset, one-time use, validators"),
        ("Accounts", "ResetEmailRoutingTests", "3", "Link addressed only to the matching account; an unknown address sends nothing"),
        ("Accounts", "ResetLinkExpiryWordingTests", "3", "Email, confirmation and invalid-link pages state the configured 12-hour expiry"),
        ("Accounts", "ResetLinkLoggingTests", "3", "Email backend flags reset links in logs"),
        ("Accounts", "RetryingSMTPBackendTests", "6", "Stalled connection retried, auth rejection not retried, partial connection cleaned up"),
        ("Accounts", "BrevoHTTPSBackendTests", "18", "HTTPS payload contract, retries, batching, fail-silently, attempt logging"),
        ("Accounts", "PasswordRuleFeedbackTests", "8", "Register page checklist agrees with validators"),
        ("Accounts", "EmailTldValidationTests", "6", "Non-existent top-level domains rejected; a typo suggestion is offered"),
        ("Accounts", "ContactValidationTests", "11", "Email and phone rules at field, form and model level, with normalisation"),
        ("Accounts", "GhanaPhoneNumberTests", "11", "Valid network prefixes, canonical form, duplicate phone rejected"),
        ("Accounts", "SessionTimeoutTests", "4", "Idle timeout, deadline rendering, session expiry"),
        ("Donors", "Stage1BoundaryTests", "4", "Age, weight and donation-interval boundaries"),
        ("Donors", "Stage2BoundaryTests", "2", "Haemoglobin and blood-pressure boundaries"),
        ("Donors", "DonationBlockingTests", "5", "Donation blocked for ineligible or unapproved donors"),
        ("Donors", "IdDocumentPrivacyTests", "4", "Document readable only by administrator"),
        ("Donors", "IdDocumentValidationTests", "3", "File type and size validation at upload"),
        ("Donors", "ContactPhoneValidationTests", "6", "Donor contact phone validated and stored in international form"),
        ("Donors", "DonationSitesTests", "8", "Approved, visible hospitals only; per-group stock, low-stock flag and ranking"),
        ("Donors", "DonorSelfServiceTests", "2", "Resubmit rejected registration, edit profile"),
        ("Donors", "AppointmentTests", "15", "Booking, staff confirm or decline, cancellation, access gates"),
        ("Inventory", "TTIGateTests", "11", "Untested bag isolation, four-marker clearance, reactive discard, expiry while awaiting the lab"),
        ("Requests_app", "CompatibilityTreeTests", "1", "Full ABO/Rh compatibility matrix (8 groups)"),
        ("Requests_app", "DenyWithAlternativesTests", "2", "Incompatible donor denial with alternatives"),
        ("Requests_app", "RequestLifecycleTests", "7", "Accept, reserve (FEFO), fulfil, reject, emergency ranking"),
        ("Requests_app", "AvailabilityFormTests", "1", "Form shows only in-stock groups"),
        ("Hospitals", "HospitalRegistrationTests", "6", "Register, duplicate rejection, pending blocking"),
        ("Hospitals", "HospitalUsernameGenerationTests", "7", "Username derived from the hospital name, collisions, length cap"),
        ("Hospitals", "HospitalContactValidationTests", "6", "Hospital contact rules on the registration and account forms"),
        ("Hospitals", "HospitalApprovalTests", "4", "Approve, reject, reject requires reason"),
        ("Hospitals", "HospitalReviewWorkflowTests", "12", "Review page, FIFO queue, search, duplicate hints"),
        ("Hospitals", "HospitalAdminEditTests", "7", "Admin edits, audit, unchanged post skipped"),
        ("Hospitals", "HospitalStaffManagementTests", "4", "Add/remove staff, self-removal guard"),
        ("Hospitals", "HospitalAdminManageTests", "4", "Directory, filters, hide toggle"),
        ("Hospitals", "HospitalAdminSiteLinkageTests", "6", "Django admin integration, approve/reject actions"),
        ("Hospitals", "HospitalReportingTests", "4", "Reports, activity feed, pending blocking"),
        ("Hospitals", "HospitalVisibleToApprovalTests", "2", "Approval as visibility gate"),
        ("Notifications", "NotificationEmailRoutingTests", "4", "Email follows the account address; one message per recipient"),
        ("Notifications", "NotificationEmailFailureTests", "2", "Failed sends logged, never raise, never break the action"),
        ("Audit", "CsvExportTests", "4", "Five report types, non-admin refused"),
        ("Audit", "PaginationTests", "2", "Donor search pagination, filter preservation"),
        ("End-to-end", "FullDemoFlowTests", "2", "Full demo story, expiry command, low-stock alert"),
        ("Render", "PageRenderTests", "8", "Every page renders for every permitted role"),
    ]


def t43_rows():
    return [
        ("Centralised donor registry",
         "Donors register once; records are verified and managed from a single platform",
         "PrivacyPartitionTests (role-based scoping), IdDocumentPrivacyTests (restricted document access), "
         "DonorSelfServiceTests (resubmit and edit), HospitalApprovalTests (hospital registration and approval), "
         "DuplicateEmailRegistrationTests, GhanaPhoneNumberTests and HospitalUsernameGenerationTests "
         "(unique, validated accounts)"),
        ("Automated blood-group compatibility matching",
         "Requests are checked against compatible stock and donors",
         "CompatibilityTreeTests (full matrix), DenyWithAlternativesTests (incompatible donor handling), "
         "RequestLifecycleTests (FEFO reservation, emergency ranking)"),
        ("Hospital inventory and request management",
         "Staff record donations, manage stock, track expiry, reserve and issue blood",
         "DonationBlockingTests (eligibility enforcement), TTIGateTests (laboratory gate, untested bag "
         "isolation, reactive discard), RequestLifecycleTests (accept, fulfil, reject), AvailabilityFormTests "
         "(in-stock groups only), FullDemoFlowTests (expiry command, low-stock alert)"),
        ("Structured organ donation workflow",
         "Donors submit requests, hospitals review, administrator approves or rejects",
         "FullDemoFlowTests (organ request lifecycle from submission to approval)"),
        ("Privacy and auditability",
         "Role-based access control, restricted document access, audit log",
         "PrivacyPartitionTests, IdDocumentPrivacyTests, ForgotPasswordGateTests and PasswordResetFlowTests "
         "(reset security), SessionTimeoutTests, CsvExportTests (audit log export), FullDemoFlowTests "
         "(audit log entries verified)"),
    ]


# --------------------------------------------------------------------------- #
# Row builders that mimic the existing tables (style comes from the table itself)
# --------------------------------------------------------------------------- #
def top_cells(row_xml: str) -> list[tuple[int, int]]:
    """Spans of the TOP-LEVEL <w:tc> cells of a row, nesting-aware (a nested
    table inside a cell must not confuse the count)."""
    out = []
    i = 0
    pat = re.compile(r"<w:tc[ >]|</w:tc>")
    while True:
        m = pat.search(row_xml, i)
        if not m:
            break
        if m.group(0) == "</w:tc>":
            i = m.end()
            continue
        start = m.start()
        depth = 0
        j = start
        while True:
            m2 = pat.search(row_xml, j)
            tag = m2.group(0)
            j = m2.end()
            if tag == "</w:tc>":
                depth -= 1
                if depth == 0:
                    out.append((start, j))
                    break
            else:
                depth += 1
        i = j
    return out


def build_row(template_row: str, cells: list[str]) -> str:
    """Fill a copy of template_row's cells with new text, preserving formatting."""
    spans = top_cells(template_row)
    assert len(spans) == len(cells), f"row needs {len(spans)} cells, got {len(cells)}"

    def fill(cell_xml: str, text: str) -> str:
        # keep <w:tcPr>, replace the first paragraph with one clean run
        mtc = re.search(r"<w:tcPr>.*?</w:tcPr>", cell_xml, re.S)
        tcpr = mtc.group(0) if mtc else ""
        mp = re.search(r"<w:p[ >].*?</w:p>", cell_xml, re.S)
        assert mp, "no paragraph in cell"
        p = mp.group(0)
        ppr_m = re.search(r"<w:pPr>.*?</w:pPr>", p, re.S)
        ppr = ppr_m.group(0) if ppr_m else ""
        rpr_m = re.search(r"<w:rPr>.*?</w:rPr>", p, re.S)
        rpr = rpr_m.group(0) if rpr_m else "<w:rPr><w:rFonts w:ascii=\"Times New Roman\" w:hAnsi=\"Times New Roman\"/></w:rPr>"
        new_p = f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{esc(text)}</w:t></w:r></w:p>"
        return "<w:tc>" + tcpr + new_p + "</w:tc>"

    return "<w:tr>" + "".join(
        fill(template_row[a:b], text) for (a, b), text in zip(spans, cells)
    ) + "</w:tr>"


def build_row_from_scratch(cells: list[str], bold: bool = False) -> str:
    rpr = '<w:rPr><w:b/><w:bCs/></w:rPr>' if bold else '<w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr>'
    tcs = "".join(
        f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>'
        f'<w:p><w:pPr><w:spacing w:after="0"/><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr></w:pPr>'
        f"<w:r>{rpr}<w:t xml:space=\"preserve\">{esc(c)}</w:t></w:r></w:p></w:tc>"
        for c in cells
    )
    return f"<w:tr>{tcs}</w:tr>"


def replace_table_rows(xml: str, table_marker: str, new_rows: list[list[str]],
                       totals_row: list[str] | None = None) -> str:
    """Replace the data rows of the table containing table_marker, keeping its
    tblPr, tblGrid and header row formatting."""
    spans = find_tables(xml)
    target = None
    for a, b in spans:
        if table_marker in xml[a:b]:
            target = (a, b)
            break
    assert target, f"table with {table_marker!r} not found"
    ta, tb = target
    t = xml[ta:tb]

    # find_rows is nesting-aware, so rows inside a nested table are skipped
    rows = find_rows(t)
    assert len(rows) >= 2, "table too small"

    # row 1 is a clean data row - use it as the formatting template
    template_row = t[rows[1][0]:rows[1][1]]
    ncells = len(top_cells(template_row))
    assert ncells == len(new_rows[0]), f"table has {ncells} cells/row"

    header = t[rows[0][0]:rows[0][1]]
    new_tbl = t[: rows[0][0]] + header
    for r in new_rows:
        new_tbl += build_row(template_row, r)
    if totals_row:
        new_tbl += build_row_from_scratch(totals_row, bold=True)
    new_tbl += t[rows[-1][1]:]

    return xml[:ta] + new_tbl + xml[tb:]


# --------------------------------------------------------------------------- #
# Main edit pass
# --------------------------------------------------------------------------- #
def apply_text_edits(xml: str) -> str:
    """All paragraph-level replacements. Each asserts its target exists."""

    def edit_para_containing(needle: str, old: str, new: str) -> None:
        nonlocal xml
        done = False
        for a, b, p in list(iter_paragraphs(xml)):
            if is_field_para(p):
                continue
            t = para_text(p)
            if needle in t and old in t:
                xml = xml[:a] + replace_para_text(p, old, new) + xml[b:]
                done = True
                break
        assert done, f"not found: {needle[:40]} / {old[:40]}"

    def replace_whole_para(needle: str, new_text: str, *, bold_prefix: str | None) -> None:
        nonlocal xml
        done = False
        for a, b, p in list(iter_paragraphs(xml)):
            if is_field_para(p):
                continue
            if needle in para_text(p):
                xml = xml[:a] + rebuild_para(p, new_text, bold_prefix=bold_prefix) + xml[b:]
                done = True
                break
        assert done, f"not found: {needle[:60]}"

    def insert_after_para(needle: str, paras: list[str], *, style: str = "body") -> None:
        nonlocal xml
        done = False
        for a, b, p in list(iter_paragraphs(xml)):
            if is_field_para(p):
                continue
            if needle in para_text(p):
                block = "".join(make_para(t, style=style) for t in paras)
                xml = xml[:b] + block + xml[b:]
                done = True
                break
        assert done, f"not found: {needle[:60]}"

    def insert_before_para(needle: str, paras: list[str], *, style: str = "body") -> None:
        nonlocal xml
        done = False
        for a, b, p in list(iter_paragraphs(xml)):
            if is_field_para(p):
                continue
            if needle in para_text(p):
                block = "".join(make_para(t, style=style) for t in paras)
                xml = xml[:a] + block + xml[a:]
                done = True
                break
        assert done, f"not found: {needle[:60]}"

    # ---- 1. Test counts -------------------------------------------------- #
    edit_para_containing(
        "evaluated through 110",
        "The system was evaluated through 110 automated tests covering unit, workflow, access-control, "
        "privacy and end-to-end scenarios, all of which passed.",
        "The system was evaluated through 264 automated tests across 47 test classes, covering boundary "
        "conditions, full workflow lifecycles, access control and per-hospital data isolation, the privacy "
        "of identity documents, input validation, email and SMS delivery, the laboratory screening gate on "
        "donated units, page rendering and an end-to-end walkthrough of the complete demo story; all of "
        "them passed.",
    )
    edit_para_containing(
        "A total of 110",
        "A total of 110 test methods were executed across 27 test classes",
        "A total of 264 test methods were executed across 47 test classes",
    )
    # extend the same sentence with the module breakdown
    edit_para_containing(
        "A total of 264 test methods",
        "covering all eight modules of the system.",
        "covering all eight modules of the system: accounts (109 tests in 16 classes), hospitals (62 tests "
        "in 11 classes), donors (49 tests in 9 classes), requests (11 tests in 4 classes), inventory (11 "
        "tests), notifications (6 tests in 2 classes), audit (6 tests in 2 classes), and the end-to-end and "
        "render suites (10 tests in 2 classes).",
    )
    edit_para_containing(
        "built in six phases using Python",  # 4.3 summary
        "Testing was carried out through 110 automated test methods across 27 test classes, covering "
        "boundary conditions, full workflow lifecycles, access control, privacy of identity documents, "
        "password-reset security, session management, page rendering and an end-to-end walkthrough of the "
        "complete demo story.",
        "Testing was carried out through 264 automated test methods across 47 test classes, covering "
        "boundary conditions, full workflow lifecycles, access control and per-hospital data isolation, "
        "the privacy of identity documents, input validation, the delivery of system email and SMS, the "
        "laboratory screening gate, password-reset security, session management, page rendering and an "
        "end-to-end walkthrough of the complete demo story.",
    )
    edit_para_containing(
        "Lastly, the automated test suite",
        "the automated test suite of 110 tests across 27 test classes serves as a practical example of how "
        "to test a multi-module web application systematically, covering boundary conditions, workflow "
        "lifecycles, access control and privacy, and an end-to-end walkthrough of the major user journeys.",
        "the automated test suite of 264 tests across 47 test classes serves as a practical example of how "
        "to test a multi-module web application systematically, covering boundary conditions, workflow "
        "lifecycles, access control and privacy, input validation, delivery-failure handling, the "
        "laboratory screening gate and an end-to-end walkthrough of the major user journeys.",
    )
    edit_para_containing(
        "Testing was carried out through 110 automated tests covering boundary",  # ch5 conclusion
        "Testing was carried out through 110 automated tests covering boundary conditions, workflow "
        "lifecycles, access control, privacy of identity documents, password-reset security, session "
        "management, page rendering and an end-to-end walkthrough of the major user journeys.",
        "Testing was carried out through 264 automated tests covering boundary conditions, workflow "
        "lifecycles, access control, privacy of identity documents, input validation, email and SMS "
        "delivery, password-reset security, session management, the laboratory screening gate, page "
        "rendering and an end-to-end walkthrough of the major user journeys.",
    )

    # ---- 2. Test categories: four -> seven -------------------------------- #
    edit_para_containing(
        "falls into four categories",
        "The test suite falls into four categories.",
        "The test suite falls into seven categories.",
    )
    # safety-gate paragraph after the workflow-tests paragraph
    insert_after_para(
        "Workflow tests exercise the full lifecycle",
        [
            "Safety-gate tests verify the laboratory gate that every donated unit must pass before it can "
            "be used. They confirm that recording a donation creates the bag in the untested state together "
            "with its laboratory screening record; that an untested bag is excluded from the stock figures "
            "and cannot be reserved, although hospital staff can see it in the inventory; that a partially "
            "entered screening neither releases nor discards the bag; that entering all four markers as "
            "non-reactive moves the bag into the available pool; that a completed screening cannot be "
            "entered a second time; that a reactive marker discards the bag with the reactive markers "
            "recorded as the reason and notifies the donor to seek counselling and confirmatory testing; "
            "that a screening which omits a marker, or which names a marker that does not exist, is "
            "rejected; and that a unit which reaches its expiry date while still awaiting the laboratory is "
            "marked expired rather than released into the pool. The daily expiry command is tested against "
            "untested bags as well as available and reserved ones.",
        ],
    )
    insert_after_para(
        "The session-timeout tests confirm",
        [
            "Validation tests check the data-entry rules that protect the quality of the records. The email "
            "tests confirm that an email address cannot be a telephone number, that malformed addresses are "
            "rejected, that an address ending in a plausible but non-existent top-level domain is refused "
            "while a real domain is accepted and a suggestion naming the likely intended domain is offered, "
            "and that a duplicate address cannot register a second account - including where the two differ "
            "only in letter case - while an address released by a deactivated account becomes available "
            "again. The Ghanaian telephone tests confirm that every valid network prefix is accepted and "
            "its network identified; that numbers longer than nine digits, numbers in the legacy "
            "leading-zero form, numbers containing letters and numbers with an unknown prefix are rejected; "
            "that spaces, dashes and parentheses are tolerated and normalised to a canonical international "
            "form; and that the same number cannot be registered twice. The same rules are verified in the "
            "model fields and on the hospital and donor forms as well as the main registration form, so "
            "that a value which reaches the database by another route still cannot be invalid. The "
            "password-checklist tests confirm that the live feedback beside the password field agrees with "
            "the configured validators, and the expiry-wording tests confirm that the reset email, the "
            "confirmation page and the invalid-link page all state the configured twelve-hour expiry.",
            "Delivery tests cover the mechanisms that operate outside the application. The password-reset "
            "routing tests confirm that the link is addressed only to the matching account and that an "
            "unregistered address produces no message at all. The SMTP tests confirm that a stalled "
            "connection is retried until it succeeds, that the backend gives up after four attempts and "
            "re-raises the error, that a rejected authentication is not retried, and that a retry cleans up "
            "the part of the connection it has opened. The HTTPS mail backend tests confirm that the "
            "request payload matches the provider's API contract, that a display name is parsed out of the "
            "sender header, that copy, blind-copy and reply-to headers are forwarded, that unreachable "
            "servers and rate-limited and server-error responses are retried while authentication, budget "
            "and malformed-payload errors are not, that a timeout is treated as a retryable failure, and "
            "that an empty recipient list is rejected before any request is made. Failure-path tests "
            "confirm that a message which cannot be sent is logged without raising, that a batch continues "
            "after one dead message, and that a notification is still stored in the application even when "
            "its email cannot be delivered, so that a mail outage can never roll back or break the action "
            "that triggered the notification.",
        ],
    )
    edit_para_containing(
        "creates an available blood bag",
        "staff record a donation, which creates an available blood bag;",
        "staff record a donation, which creates an untested blood bag, and the laboratory screening that "
        "follows clears it into the available pool;",
    )
    # appointment sentence for 4.1.3 workflow paragraph
    edit_para_containing(
        "and the administrator’s dashboard and audit log reflect every step",
        "and the administrator’s dashboard and audit log reflect every step.",
        "a donor books a donation appointment from the donation sites directory and hospital staff confirm "
        "it; and the administrator’s dashboard and audit log reflect every step.",
    )

    # ---- 3. Requirements (3.2.3) ------------------------------------------ #
    replace_whole_para(
        "Donation recording: Hospital staff shall be able to record",
        "Donation recording: Hospital staff shall be able to record a completed donation for an eligible "
        "donor. The system shall enforce eligibility at the time of recording, so that a donation cannot be "
        "recorded for a donor whose registration is not approved, who has no recent eligible screening, or "
        "who has not yet waited the required interval. Each recorded donation shall create a corresponding "
        "blood bag in the hospital’s inventory with a computed expiry date, and shall open a laboratory "
        "screening record for that donation. The new bag shall be created in the untested state, and shall "
        "not be counted in stock, offered to a request or issued until the laboratory has recorded a "
        "non-reactive result for every marker of the transfusion-transmissible infection panel (HIV, "
        "hepatitis B, hepatitis C and syphilis).",
        bold_prefix="Donation recording:",
    )
    insert_after_para(
        "until the laboratory has recorded a non-reactive result",
        [
            "Laboratory screening: Hospital staff shall be able to enter the laboratory results for a "
            "recorded donation, one result for each marker of the transfusion-transmissible infection panel "
            "- HIV, hepatitis B, hepatitis C and syphilis. All four results shall be required before the "
            "screening is treated as complete, and an incomplete screening shall neither release nor "
            "discard the unit. The outcome of the screening shall gate the blood bag: the bag shall move "
            "from untested to available only when every result is non-reactive, and shall be discarded when "
            "any result is reactive, with the reactive markers recorded as the reason and the donor "
            "notified and advised to seek counselling and confirmatory testing. A screening that has been "
            "completed shall not be entered a second time, and a unit that reaches its expiry date before "
            "the laboratory clears it shall be marked expired rather than released.",
            "Donation appointments: A donor shall be able to see the hospitals that are open to donations, "
            "the blood groups each hospital holds in available stock, and the groups in which it is short, "
            "and shall be able to book a visit to a chosen hospital on a proposed date. The hospital's "
            "staff shall be able to confirm or decline the booking with a note, and the donor shall see the "
            "outcome and be able to cancel a booking that is still pending. A booking shall be refused for "
            "a donor whose registration is not approved, for a hospital that is not visible to donors, for "
            "a date in the past or beyond the permitted booking window, and where the donor already holds a "
            "pending booking at that hospital.",
        ],
        style="list",
    )
    replace_whole_para(
        "Inventory management: The system shall maintain",
        "Inventory management: The system shall maintain, for each registered hospital, a record of every "
        "blood bag and its status. The possible statuses of a bag are untested, available, reserved, "
        "issued, expired and discarded, and a bag that has just been recorded begins as untested. The "
        "system shall calculate stock levels from the available bags rather than storing a separate "
        "counter, so that the displayed stock is always consistent with the underlying records; units "
        "awaiting the laboratory shall be visible to hospital staff but excluded from the stock figures "
        "and unavailable for reservation. It shall identify bags that are close to their expiry date, mark "
        "bags that have passed their expiry date - including bags still awaiting the laboratory - and "
        "notify hospital staff when the available stock of any blood group falls below a defined "
        "threshold.",
        bold_prefix="Inventory management:",
    )
    edit_para_containing(
        "Where an emergency request cannot be met from available stock, the system shall send",
        "the system shall send an urgent broadcast notification to the compatible donors registered in the "
        "hospital’s city.",
        "the system shall send an urgent broadcast notification to the compatible donors registered in the "
        "hospital’s city. Only bags that have passed the laboratory screening gate shall be eligible for "
        "reservation; a unit that is still untested shall not appear in the stock a request can draw on.",
    )
    edit_para_containing(
        "The system shall prevent a bag from being reserved or issued twice",
        "The system shall prevent a bag from being reserved or issued twice, even when two users act at the "
        "same time.",
        "The system shall prevent a bag from being reserved or issued twice, even when two users act at the "
        "same time. The release of a screened unit into the available pool, the discarding of a reactive "
        "unit and the expiry of a past-date unit shall each be applied through a single audited code path, "
        "so that a status change and its audit entry cannot be recorded separately.",
    )

    # ---- 4. Data design (3.3.2) ------------------------------------------- #
    edit_para_containing(
        "relational database containing eleven tables",
        "a relational database containing eleven tables",
        "a relational database containing thirteen tables",
    )
    edit_para_containing(
        "The BloodBag table represents a single unit",
        "current status (available, reserved, issued, expired or discarded)",
        "current status (untested, available, reserved, issued, expired or discarded)",
    )
    insert_after_para(
        "the review status (pending, requested, approved or rejected) and the timestamps of creation and "
        "decision",
        [
            "The laboratory screening of each donation is held in its own table, linked one-to-one to the "
            "donation, which stores one result for each marker of the infection panel, the staff member who "
            "entered the results, the time of entry and the reason recorded when a unit is discarded. The "
            "record is kept after the decision, so that the reason a unit was discarded survives alongside "
            "the audit trail. An Appointment table records a donor's request to donate at a chosen hospital "
            "on a proposed date, together with the donor's note, the hospital's decision and note, and the "
            "time of the decision.",
        ],
    )
    edit_para_containing(
        "This design was chosen deliberately",
        "This design was chosen deliberately, because in a real hospital two staff members could act on the "
        "same request or the same stock at almost the same moment, and the system must behave correctly in "
        "that situation.",
        "This design was chosen deliberately, because in a real hospital two staff members could act on the "
        "same request or the same stock at almost the same moment, and the system must behave correctly in "
        "that situation. A further decision concerns the safety gate: every change to a bag's status passes "
        "through a single service function, so that a unit cannot reach the available, reserved or "
        "discarded state without the change and its reason being written to the audit log at the same "
        "moment.",
    )
    edit_para_containing(
        "the design of the eleven-table database",
        "the design of the eleven-table database",
        "the design of the thirteen-table database",
    )

    # ---- 5. Matching component + diagrams (3.3.3) -------------------------- #
    edit_para_containing(
        "donors who can donate immediately are ranked first",
        "For emergency requests, donors who can donate immediately are ranked first, because the need is "
        "immediate.",
        "For emergency requests, donors who can donate immediately are ranked first, because the need is "
        "immediate. The pool of bags against which the component matches is the set of units that have "
        "passed the laboratory screening gate; a unit still awaiting the laboratory is invisible to the "
        "matching process, however recently it was collected.",
    )
    edit_para_containing(
        "no bag can be reserved by two requests simultaneously",
        "the required number of compatible bags are located in first-expiry-first-out order",
        "the required number of compatible bags are located in first-expiry-first-out order among the units "
        "that have passed the laboratory screening gate",
    )
    edit_para_containing(
        "presents a flowchart of the blood request lifecycle",
        "locates compatible bags in first-expiry-first-out order, reserves them",
        "locates compatible bags in first-expiry-first-out order among the units cleared by the laboratory "
        "screening gate, reserves them",
    )
    edit_para_containing(
        "Donation Recording and Inventory Management process creates a Blood Bag Inventory record",
        "creates a Blood Bag Inventory record linked to the donor and the hospital.",
        "creates a Blood Bag Inventory record linked to the donor and the hospital in the untested state, "
        "together with a laboratory screening record; the unit joins the available stock in that store only "
        "once the screening results have been entered and every marker is non-reactive, and a reactive unit "
        "is discarded instead.",
    )

    # ---- 6. Security + chapter three summary ------------------------------- #
    edit_para_containing(
        "Audit trail: Every important action",
        "This includes the approval and rejection of donors, the creation and status changes of blood bags, "
        "the acceptance, rejection and fulfilment of requests, and the progress of organ donation requests.",
        "This includes the approval and rejection of donors, the creation of blood bags in the untested "
        "state and every subsequent change of their status, the entry of laboratory screening results and "
        "the release or discard of the units they decide, the acceptance, rejection and fulfilment of "
        "requests, and the progress of organ donation requests.",
    )
    edit_para_containing(
        "centred on role-based access control",
        "centred on role-based access control, the restricted handling of identity documents, privacy-aware "
        "queries, session and password security, and a complete audit trail.",
        "centred on role-based access control, the restricted handling of identity documents, privacy-aware "
        "queries, session and password security, the laboratory screening gate that holds every donated "
        "unit out of the usable stock until it is cleared, and a complete audit trail.",
    )

    # ---- 7. Chapter four phases -------------------------------------------- #
    replace_whole_para(
        "Phase 2:  Donor Screening and Donation Recording",
        "Phase 2: Donor Screening and Donation Recording. The second phase implemented the two-stage "
        "screening process and the recording of donations. When hospital staff select an approved donor for "
        "screening, the system first runs the stage-one eligibility check, which evaluates the donor’s age, "
        "weight and the interval since the last donation against the thresholds configured in the "
        "application (see Table 3.2 in Chapter Three). The stage-one check returns one of three outcomes: "
        "eligible, temporarily deferred, or permanently ineligible. Hospital staff then enter the donor’s "
        "haemoglobin level and blood pressure readings for the stage-two clinical screening. The combined "
        "outcome of both stages is recorded as a screening record, and the donor is notified. Recording a "
        "donation enforces eligibility at the point of action: the system checks that the donor’s "
        "registration is approved, that a recent screening exists with an eligible outcome, and that the "
        "required interval since the last donation has elapsed. A successful recording creates a donation "
        "record and a corresponding blood bag in the hospital’s inventory, with the expiry date computed as "
        "the collection date plus the configured shelf life of thirty-five days. The new bag is created in "
        "the untested state, and the laboratory screening record for the donation is opened at the same "
        "moment, so that no unit can enter the stock pool before the laboratory has cleared it. The member "
        "of staff who recorded the donation is taken straight to the laboratory screening queue, which "
        "lists the hospital’s donations awaiting screening oldest first. Entering the four results - HIV, "
        "hepatitis B, hepatitis C and syphilis - completes the screening: when every result is non-reactive "
        "the bag moves from untested to available and enters the stock pool, and when any result is "
        "reactive the bag is discarded, with the reactive markers recorded as the reason, and the donor is "
        "notified and advised to seek counselling and confirmatory testing. While the screening is "
        "incomplete the bag is visible in the hospital’s inventory but is excluded from the stock figures "
        "and cannot be reserved, and a unit that reaches its expiry date before the laboratory clears it is "
        "marked expired instead of being released. The same phase added the donor-facing donation sites "
        "directory, from which an approved donor can book a donation appointment at a chosen hospital for "
        "staff to confirm or decline.",
        bold_prefix=None,
    )
    replace_whole_para(
        "Phase 3:  Blood Bag Inventory and Expiry Tracking",
        "Phase 3: Blood Bag Inventory and Expiry Tracking. The third phase added the inventory dashboard "
        "and the expiry tracking mechanism. The inventory is displayed on a per-hospital basis, with stock "
        "levels for each blood group computed from the available bags rather than stored as a separate "
        "counter. This design ensures that the displayed stock is always consistent with the underlying "
        "records. Units awaiting laboratory screening are shown separately from the available stock, so "
        "that hospital staff can see what is still in the laboratory without it being counted as usable "
        "blood. The system identifies bags that are within seven days of their expiry date and highlights "
        "them for attention. A daily management command scans every bag that has not yet reached a final "
        "state - untested, available and reserved alike - and changes the status of any bag whose expiry "
        "date has passed to expired, recording the event in the audit log and sending a low-stock "
        "notification to the hospital’s staff when the available stock of any blood group falls below the "
        "configured threshold.",
        bold_prefix=None,
    )
    edit_para_containing(
        "presents hospital staff with a ranked list of compatible donors",
        "rioritizing those who can donate immediately.",
        "prioritizing those who can donate immediately. Only bags that have cleared laboratory screening "
        "take part in the reservation that follows; the matching and reservation code never sees a unit "
        "that is still untested.",
    )
    edit_para_containing(
        "walks through the complete demo story in a single test method",
        "donation recording → patient blood request",
        "donation recording → laboratory screening clears the unit → patient blood request",
    )

    # ---- 8. Session security + heading number ------------------------------- #
    edit_para_containing(
        "Password reset links expire",
        "Password reset links expire after one day.",
        "Password reset links expire after twelve hours.",
    )
    edit_para_containing(
        "4.2.3   Performance Evaluation",
        "4.2.3   Performance Evaluation",
        "4.2.4   Performance Evaluation",
    )

    # ---- 9. Table 4.3 caption ------------------------------------------------ #
    edit_para_containing(
        "Table 4.2: Evaluation criteria and supporting test evidence",
        "Table 4.2: Evaluation criteria and supporting test evidence",
        "Table 4.3: Evaluation criteria and supporting test evidence",
    )

    # ---- 10. Appointments feature entry (4.2.3) ------------------------------ #
    fig49 = None
    for a, b, p in iter_paragraphs(xml):
        if para_text(p).strip().startswith("Figure 4.9"):
            fig49 = (a, b, p)
    assert fig49, "Figure 4.9 paragraph not found"
    entry = (
        make_para("Figure 4.10: Donation sites directory and appointment booking")
        + make_para("WHERE TO DONATE (DONATION SITES AND APPOINTMENTS)")
        + make_para(
            "The donation sites directory is the page an approved donor uses to decide where to give "
            "blood. It lists the hospitals that are open to donations, and beside each hospital it shows "
            "the blood groups that hospital currently holds in available stock, with the groups that have "
            "fallen below the low-stock threshold flagged. The list is ordered so that it answers two "
            "questions at once: hospitals in the donor’s own city are ranked first, and within that group "
            "the hospitals that are short of the donor’s own blood group come first, carrying a badge that "
            "marks the need. A donor can therefore see both where they can go and where they would be most "
            "useful. Eligibility is not decided on this page: the directory is informational, and the "
            "standing eligibility rules are still applied by hospital staff at the time of screening."
        )
        + make_para(
            "From the directory the donor can book a visit. The booking form asks for the day the donor "
            "proposes to come in and an optional note for the hospital, and it accepts only a date between "
            "today and sixty days ahead. A booking is refused unless the donor’s registration has been "
            "approved, and a donor who already holds a pending booking at the same hospital is shown that "
            "booking instead of being offered a second one. When the booking is created, the staff of the "
            "chosen hospital are notified immediately, with the donor’s name and blood group in the "
            "message, and the appointment enters a pending state that both sides can see."
        )
        + make_para(
            "Hospital staff review bookings in their appointment inbox, which lists the hospital’s "
            "appointments newest first with a count of those still pending. Staff either confirm a booking "
            "or decline it with a note, and the donor is notified of the decision either way; the "
            "confirmation message reminds the donor to bring their government identity document. A donor "
            "can cancel a booking that has not yet been decided, which closes the appointment and tells "
            "the hospital’s staff. Every step of the workflow - the booking, the cancellation, the "
            "confirmation and the decline - is recorded in the audit log with the actor and the date, so "
            "the appointment record gives both sides a shared status instead of an untracked telephone "
            "call. The directory, the booking form, the donor’s appointment list and the staff inbox are "
            "exercised by the appointment and donation-site tests described in Section 4.1.3 "
            "(DonationSitesTests and AppointmentTests)."
        )
    )
    # insert before the (renamed) Performance Evaluation heading
    target = None
    for a, b, p in iter_paragraphs(xml):
        if "Performance Evaluation" in para_text(p) and "4.2.4" in para_text(p):
            target = a
            break
    assert target, "Performance Evaluation heading not found"
    xml = xml[:target] + entry + xml[target:]

    # ---- 11. List of Figures line ------------------------------------------- #
    # after the TOC paragraph containing "Figure 4.9\t"
    done = False
    for a, b, p in list(iter_paragraphs(xml)):
        t = para_text(p)
        if "Figure 4.9" in t and "\t" in p:
            block = make_para("Figure 4.10\tDonation sites directory and appointment booking")
            xml = xml[:b] + block + xml[b:]
            done = True
            break
    # TOC is a field; if not found as plain para, leave it to Word's TOC update
    if not done:
        print("  note: List of Figures entry not inserted as text (update TOC in Word instead)")

    return xml


def apply_tables(xml: str) -> str:
    xml = replace_table_rows(
        xml,
        "PrivacyPartitionTests",
        [list(r) + ["All passed"] for r in t42_rows()],
        totals_row=["All modules", "47 test classes", "264",
                    "Boundary, workflow, safety-gate, access-control, validation, delivery and render tests",
                    "All passed"],
    )
    xml = replace_table_rows(
        xml,
        "Centralised donor registry",
        [list(r) for r in t43_rows()],
    )
    return xml


def main() -> None:
    data = SRC.read_bytes()
    backup = SRC.with_name(SRC.stem + "_BACKUP.docx")
    if not backup.exists():
        backup.write_bytes(data)
        print(f"backup written: {backup.name}")

    zin = zipfile.ZipFile(SRC)
    xml = zin.read("word/document.xml").decode("utf-8")
    original = xml

    xml = apply_text_edits(xml)
    xml = apply_tables(xml)

    assert xml != original
    # sanity: parse
    import xml.etree.ElementTree as ET

    ET.fromstring(xml)

    out = SRC.with_name(SRC.stem + "_UPDATED.docx")
    with zipfile.ZipFile(io.BytesIO(data)) if False else zipfile.ZipFile(SRC) as zin2:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin2.infolist():
                content = zin2.read(item.filename)
                if item.filename == "word/document.xml":
                    content = xml.encode("utf-8")
                zout.writestr(item, content)
    print(f"written: {out.name} ({out.stat().st_size} bytes) - master untouched")


import io  # noqa: E402

if __name__ == "__main__":
    main()
