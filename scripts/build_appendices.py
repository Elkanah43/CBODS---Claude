"""Build the CBODS report appendices (Appendix A-G) as a standalone Word document.

Every listing is monospaced (Consolas 8.5pt, single-spaced, no space between
paragraphs), with a bold caption line above each listing and a page break
between appendices. The document is written as raw OOXML (no python-docx or
other dependency) using the same minimal but valid package layout Word itself
produces for simple documents.

Usage:
    python scripts\\build_appendices.py
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import re
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Appendix plan: (appendix title, [ (caption, source path, start_line, end_line), ... ])
# Line numbers are 1-based and inclusive, matching the editor's display, so a
# reviewer can find the same code with the line numbers visible in Word.
# None for start/end means the whole file.
# ---------------------------------------------------------------------------

APPENDICES: list[tuple[str, list[tuple[str, str, int | None, int | None]]]] = [
    (
        "APPENDIX A: PROJECT CONFIGURATION (cbods/settings.py)",
        [
            (
                "Listing A.1: cbods/settings.py — central configuration: security settings, "
                "session timeout, and the configurable clinical thresholds of Table 3.2",
                "cbods/settings.py", None, None,
            ),
        ],
    ),
    (
        "APPENDIX B: DATA MODELS (models.py of each application)",
        [
            ("Listing B.1: accounts/models.py — custom user model with the four system roles",
             "accounts/models.py", None, None),
            ("Listing B.2: hospitals/models.py — Hospital, StaffProfile, HospitalApprovalStatus",
             "hospitals/models.py", None, None),
            ("Listing B.3: donors/models.py — Donor, ScreeningRecord, Appointment and status types",
             "donors/models.py", None, None),
            ("Listing B.4: inventory/models.py — BloodBag, Donation, TTITestRecord and bag states",
             "inventory/models.py", None, None),
            ("Listing B.5: requests_app/models.py — BloodRequest and request states",
             "requests_app/models.py", None, None),
            ("Listing B.6: organs/models.py — OrganDonationRequest and review states",
             "organs/models.py", None, None),
            ("Listing B.7: notifications/models.py — Notification",
             "notifications/models.py", None, None),
            ("Listing B.8: audit/models.py — AuditLog",
             "audit/models.py", None, None),
        ],
    ),
    (
        "APPENDIX C: BUSINESS LOGIC (SERVICE LAYER)",
        [
            ("Listing C.1: donors/services.py — two-stage donor eligibility screening (Section 3.2.3, Table 3.2)",
             "donors/services.py", None, None),
            ("Listing C.2: requests_app/compatibility.py — ABO/Rh compatibility matrix and FEFO bag selection (Table 3.1)",
             "requests_app/compatibility.py", None, None),
            ("Listing C.3: inventory/services.py — stock computation, donation recording, TTI laboratory gate, expiry",
             "inventory/services.py", None, None),
            ("Listing C.4: requests_app/services.py — race-safe reserve/issue under transaction.atomic() (Section 4.2.3)",
             "requests_app/services.py", None, None),
            ("Listing C.5: hospitals/services.py — hospital reporting aggregates and activity feed (Figure 4.9)",
             "hospitals/services.py", None, None),
            ("Listing C.6: audit/services.py — audit-trail entry point and system totals",
             "audit/services.py", None, None),
            ("Listing C.7: notifications/services.py — in-app + email notification dispatch",
             "notifications/services.py", None, None),
        ],
    ),
    (
        "APPENDIX D: KEY VIEWS (SELECTED)",
        [
            ("Listing D.1: accounts/views.py — role-based dashboard dispatch (Figures 4.5-4.8)",
             "accounts/views.py", None, None),
            ("Listing D.2: donors/views.py, id_document view — the only path to a donor's ID scan (Section 3.3.6)",
             "donors/views.py", 280, 291,
             ),
            ("Listing D.3: inventory/views.py — TTI screening entry (Section 4.1.2, Phase 2)",
             "inventory/views.py", None, None),
            ("Listing D.4: organs/views.py — organ donation request and review workflow",
             "organs/views.py", None, None),
        ],
    ),
    (
        "APPENDIX E: ACCESS CONTROL AND SECURITY HELPERS",
        [
            ("Listing E.1: accounts/decorators.py — role_required decorator enforcing role-based access (Section 3.3.6)",
             "accounts/decorators.py", None, None),
            ("Listing E.2: hospitals/decorators.py — require_approved_hospital gate",
             "hospitals/decorators.py", None, None),
            ("Listing E.3: accounts/password_rules.py — live password-rule checklist driven by settings",
             "accounts/password_rules.py", None, None),
        ],
    ),
    (
        "APPENDIX F: URL ROUTING AND MANAGEMENT COMMAND",
        [
            ("Listing F.1: cbods/urls.py — root URLconf (note MEDIA_ROOT is deliberately not served)",
             "cbods/urls.py", None, None),
            ("Listing F.2: donors/urls.py — donor, appointment and approval routes",
             "donors/urls.py", None, None),
            ("Listing F.3: requests_app/urls.py — blood request routes",
             "requests_app/urls.py", None, None),
            ("Listing F.4: organs/urls.py — organ request and review routes",
             "organs/urls.py", None, None),
            ("Listing F.5: inventory/urls.py — stock, donation and TTI routes",
             "inventory/urls.py", None, None),
            ("Listing F.6: audit/urls.py — admin dashboard, audit log and CSV export routes",
             "audit/urls.py", None, None),
            ("Listing F.7: notifications/urls.py — notification inbox route",
             "notifications/urls.py", None, None),
            ("Listing F.8: accounts/urls.py — registration, login and password-reset routes",
             "accounts/urls.py", None, None),
            ("Listing F.9: hospitals/urls.py — hospital registration, approval and report routes",
             "hospitals/urls.py", None, None),
            ("Listing F.10: inventory/management/commands/expire_bags.py — daily expiry command (Section 4.1.2, Phase 3)",
             "inventory/management/commands/expire_bags.py", None, None),
        ],
    ),
    (
        "APPENDIX G: END-TO-END TEST (cbods/tests_e2e.py)",
        [
            ("Listing G.1: cbods/tests_e2e.py — the full demo story driven over HTTP: registration with ID, "
             "approval, screening, donation, TTI clearance, request/reserve/issue, emergency broadcast, "
             "organ approval, and audit-log verification (Section 4.1.3)",
             "cbods/tests_e2e.py", None, None),
        ],
    ),
]

# ---------------------------------------------------------------------------
# OOXML helpers
# ---------------------------------------------------------------------------

_FONT = "Consolas"
_SIZE_HALF_POINTS = 17  # 8.5 pt


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _run(text: str, *, bold: bool = False, italic: bool = False, mono: bool = False,
         size: int | None = None, color: str | None = None) -> str:
    props = ""
    if mono:
        props += f'<w:rFonts w:ascii="{_FONT}" w:hAnsi="{_FONT}" w:cs="{_FONT}"/>'
    if bold:
        props += "<w:b/>"
    if italic:
        props += "<w:i/>"
    # CT_RPr schema order: color comes before sz/szCs.
    if color:
        props += f'<w:color w:val="{color}"/>'
    if size:
        props += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    return f'<w:r><w:rPr>{props}</w:rPr><w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'


def _para(runs: str, *, style: str | None = None, spacing: str = "",
          keep_next: bool = False, indent: str = "") -> str:
    props = ""
    if style:
        props += f'<w:pStyle w:val="{style}"/>'
    if keep_next:
        props += "<w:keepNext/>"
    if indent:
        props += indent
    props += spacing
    rpr = f"<w:pPr>{props}</w:pPr>" if props else ""
    return f"<w:p>{rpr}{runs}</w:p>"


MONO_SPACING = (
    '<w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>'
)


def code_paragraph(line: str) -> str:
    """One monospaced paragraph; a blank source line becomes an empty paragraph."""
    run = _run(line if line.strip() else "", mono=True, size=_SIZE_HALF_POINTS)
    return _para(run, spacing=MONO_SPACING)


def caption_paragraph(text: str) -> str:
    runs = _run(text, bold=True)
    return _para(runs, spacing='<w:spacing w:before="240" w:after="120"/>', keep_next=True)


def heading_paragraph(text: str, size_half_points: int = 32) -> str:
    size = size_half_points
    runs = _run(text, bold=True, size=size)
    return _para(
        runs,
        spacing=f'<w:spacing w:before="0" w:after="240"/>',
        keep_next=True,
    )


def page_break_paragraph() -> str:
    return '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'


def file_heading_paragraph(path: str) -> str:
    return _para(
        _run(f"File: {path}", italic=True, size=18, color="404040"),
        spacing='<w:spacing w:before="0" w:after="60"/>',
        keep_next=True,
    )


# ---------------------------------------------------------------------------
# Content assembly
# ---------------------------------------------------------------------------

def read_listing(path: str, start: int | None, end: int | None) -> list[str]:
    src = (PROJECT_ROOT / path).read_text(encoding="utf-8")
    lines = src.splitlines()
    if start is not None or end is not None:
        s = (start or 1) - 1
        e = end if end is not None else len(lines)
        lines = lines[s:e]
    if lines and lines[-1].strip() == "":
        lines = lines[:-1]  # drop one trailing blank line
    return lines


def _is_sentinel(entry: tuple) -> bool:
    return len(entry) == 4 and entry[3] == "None-sentinel"


def build_document_xml(appendices=APPENDICES) -> str:
    body: list[str] = []

    # Title page content (kept minimal; the section inherits document defaults)
    body.append(heading_paragraph("CBODS — CENTRALISED BLOOD & ORGAN DONATION SYSTEM", 36))
    body.append(heading_paragraph("APPENDICES", 40))
    body.append(_para(_run("Source code listings supporting Chapters 3 and 4", italic=True)))
    body.append(_para(_run(f"Generated { _dt.date.today().isoformat() } from the project repository.", italic=True, size=18, color="808080")))
    body.append(page_break_paragraph())

    for idx, app in enumerate(appendices):
        title, listings = app[0], app[1]
        body.append(heading_paragraph(title, 28))

        for entry in listings:
            caption, path, start, end = entry[0], entry[1], entry[2], entry[3]
            lines = read_listing(path, start, end)
            body.append(caption_paragraph(caption))
            body.append(file_heading_paragraph(path))
            for line in lines:
                body.append(code_paragraph(line))

        if idx < len(appendices) - 1:
            body.append(page_break_paragraph())

    heading_block = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    )
    return heading_block


# ---------------------------------------------------------------------------
# Minimal but valid .docx package
# ---------------------------------------------------------------------------

CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
    '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
    '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
    "</Relationships>"
)

DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)

CORE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    "<dc:title>CBODS Report Appendices</dc:title>"
    "<dc:subject>Source code appendices for the CBODS final-year report</dc:subject>"
    f"<dc:creator>CBODS build script</dc:creator>"
    "</cp:coreProperties>"
)

APP_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
    "<Application>CBODS build_appendices.py</Application>"
    "</Properties>"
)

STYLES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:docDefaults>"
    "<w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>'
    '<w:sz w:val="22"/><w:szCs w:val="22"/>'
    "</w:rPr></w:rPrDefault>"
    "<w:pPrDefault><w:pPr>"
    '<w:spacing w:before="0" w:after="160" w:line="259" w:lineRule="auto"/>'
    "</w:pPr></w:pPrDefault>"
    "</w:docDefaults>"
    "</w:styles>"
)


def write_docx(out_path: Path, document_xml: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES_XML)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("docProps/core.xml", CORE_XML)
        z.writestr("docProps/app.xml", APP_XML)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/styles.xml", STYLES_XML)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build CBODS report appendices docx")
    ap.add_argument("-o", "--output", default="CBODS_APPENDICES.docx")
    args = ap.parse_args()
    xml = build_document_xml()
    out = Path(args.output)
    write_docx(out, xml)
    total_lines = 0
    for _title, listings in APPENDICES:
        for _cap, path, start, end in listings:
            total_lines += len(read_listing(path, start, end))
    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")
    print(f"Appendices: {len(APPENDICES)}, listings: "
          f"{sum(len(l) for _t, l in APPENDICES)}, total code lines: {total_lines:,}")


if __name__ == "__main__":
    main()
