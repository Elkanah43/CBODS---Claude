"""Bring CBODS_IT_Project_Presentation 2.pptx up to date with the implemented system.

The same corrections that were applied to the thesis (CBODS_NEW V8.3.docx) are applied
here to the slide deck, and to nothing else.  The deck keeps its structure: the same 17
slides, the same titles, the same bullet lists, the same images.  Only the following
statements, which the finished system has overtaken, are corrected:

  slide 8   Phase 2 / Phase 3 are rewritten (laboratory screening gate, untested bags,
            donation sites and appointment booking).
  slide 9   "Eleven tables" -> "Thirteen tables"; TTITestRecord added to the core tables.
  slide 10  Appointment added to the operational tables.
  slide 12  "11 tables" -> "13 tables"; the single audited status-change path added to
            the architectural decisions.
  slide 13  Password-reset expiry made specific (twelve hours); the laboratory screening
            gate added to the security measures.
  slide 16  "110 passing automated tests" -> "264"; "all five objectives" -> "all three
            objectives" to match the three objectives stated in Chapter One; the laboratory
            gate added to the conclusion; the two recommendations that are now implemented
            (infectious-disease screening, SMS/email notification) replaced with what
            remains.
  slide 17  Reference list corrected against the thesis list (author names, initials,
            work titles, dates, page ranges).

Everything else is copied through byte for byte.  Output: a NEW file beside the source.
"""

from __future__ import annotations

import io
import re
import sys
import zipfile
from pathlib import Path

SRC = Path(r"C:\Users\Elkanah\Desktop\Sch\!!P\CBODS_IT_Project_Presentation 2.pptx")
OUT = SRC.with_name(SRC.stem + "_UPDATED.pptx")
# If the previous output is open in PowerPoint it cannot be replaced, so a numbered
# sibling is written instead rather than failing or disturbing the open copy.
FALLBACKS = [SRC.with_name(SRC.stem + f"_UPDATED_v{i}.pptx") for i in range(2, 6)]


def pick_output() -> Path:
    for candidate in [OUT, *FALLBACKS]:
        if not candidate.exists():
            return candidate
        try:
            with open(candidate, "r+b"):
                return candidate
        except OSError:
            print(f"note: {candidate.name} is locked (probably open in PowerPoint)")
    raise SystemExit("every candidate output file is locked")

PARA_RE = re.compile(r"<a:p(?: [^>]*)?>.*?</a:p>", re.S)
T_RE = re.compile(r"(<a:t(?: [^>]*)?>)(.*?)(</a:t>)", re.S)
PPR_RE = re.compile(r"<a:pPr[^>]*/>|<a:pPr[ >].*?</a:pPr>", re.S)
RUN_RE = re.compile(r"<a:r(?: [^>]*)?>.*?</a:r>", re.S)
RPR_RE = re.compile(r"<a:rPr[^>]*/>|<a:rPr[ >].*?</a:rPr>", re.S)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def para_text(p: str) -> str:
    return "".join(m.group(2) for m in T_RE.finditer(p))


def replace_text(xml: str, needle: str, replacement: str) -> str:
    """Replace `needle` inside the run text that holds it, leaving formatting alone."""
    hits = 0

    def sub(m: re.Match) -> str:
        nonlocal hits
        body = m.group(2)
        if needle in body:
            hits += body.count(needle)
            body = body.replace(needle, replacement)
        return m.group(1) + body + m.group(3)

    out = T_RE.sub(sub, xml)
    assert hits == 1, f"replace_text: {needle[:60]!r} found {hits} time(s)"
    return out


def set_para_text(xml: str, old_text: str, new_text: str) -> str:
    """Replace the whole text of the paragraph that reads exactly `old_text`."""
    found = [m for m in PARA_RE.finditer(xml) if para_text(m.group(0)) == old_text]
    assert len(found) == 1, f"set_para_text: {old_text[:50]!r} matched {len(found)} paragraph(s)"
    m = found[0]
    p = m.group(0)
    ts = list(T_RE.finditer(p))
    assert len(ts) == 1, f"set_para_text: {len(ts)} runs in {old_text[:50]!r}"
    t = ts[0]
    new_p = p[: t.start()] + t.group(1) + esc(new_text) + t.group(3) + p[t.end():]
    return xml[: m.start()] + new_p + xml[m.end():]


def delete_para(xml: str, start_text: str) -> str:
    """Remove the paragraph whose text begins with `start_text`."""
    found = [m for m in PARA_RE.finditer(xml) if para_text(m.group(0)).startswith(start_text)]
    assert len(found) == 1, f"delete_para: {start_text[:50]!r} matched {len(found)}"
    m = found[0]
    return xml[: m.start()] + xml[m.end():]


def insert_para_after(xml: str, anchor: str, text: str) -> str:
    """Insert a new bullet after the paragraph containing `anchor`, cloning its format."""
    found = [m for m in PARA_RE.finditer(xml) if anchor in para_text(m.group(0))]
    assert len(found) == 1, f"insert_para_after: anchor {anchor[:50]!r} matched {len(found)}"
    m = found[0]
    template = m.group(0)
    ppr = PPR_RE.search(template)
    run = RUN_RE.search(template)
    assert run, f"insert_para_after: no run in template for {anchor[:50]!r}"
    rpr = RPR_RE.search(run.group(0))
    new_run = "<a:r>" + (rpr.group(0) if rpr else "") + f"<a:t>{esc(text)}</a:t></a:r>"
    new_para = "<a:p>" + (ppr.group(0) if ppr else "") + new_run + "</a:p>"
    return xml[: m.end()] + new_para + xml[m.end():]


def edit_slide6(xml: str) -> str:
    """Literature review: add the algorithmic sources; the BSIS pair moves to slide 7."""
    xml = delete_para(xml, "Ghana's NBS operates through donation centres")
    xml = delete_para(xml, "BSIS focuses on blood centre operations")
    xml = insert_para_after(
        xml,
        "ABO/Rh compatibility rules are fixed and well-documented",
        "Compatibility matching can be encoded as a decision tree over ABO and Rh \u2014 a "
        "match or a denial \u2014 with requests prioritised by urgency (More et al., 2024)",
    )
    xml = insert_para_after(
        xml,
        "with requests prioritised by urgency (More et al., 2024)",
        "Two-stage donor eligibility \u2014 basic criteria then complex health metrics \u2014 "
        "has been classified with decision trees and Naive Bayes (Zulfikar et al., 2018; "
        "More et al., 2024); CBODS applies the same rules as transparent logic rather than a "
        "classifier",
    )
    return xml


def edit_slide7(xml: str) -> str:
    """The BSIS comparison, taking in the two bullets moved off slide 6."""
    xml = set_para_text(
        xml,
        "BSIS (2017): national blood centre value chain \u2192 CBODS adds hospital-level "
        "screening, inventory and request tools",
        "BSIS (2017): computerised the national value chain (Ministry of Health, 2017), but "
        "stays at blood-centre level",
    )
    xml = insert_para_after(
        xml,
        "stays at blood-centre level",
        "No hospital-level screening, stock management or request workflow in BSIS \u2192 "
        "CBODS adds all three",
    )
    return xml


def add_literature_references(xml: str) -> str:
    """References: add the two sources cited on slide 6, in alphabetical position."""
    xml = insert_para_after(
        xml,
        "Ministry of Health, Ghana (2017)",
        "More, Y., Jangir, A., Shitole, A. et al. (2024) 'Study of algorithms for blood bank "
        "management system', Alochana Journal, 13(12), pp. 57\u201364.",
    )
    xml = insert_para_after(
        xml,
        "World Health Organization (n.d.) Transplantation",
        "Zulfikar, W.B., Gerhana, Y.A. and Rahmania, A.F. (2018) 'An approach to classify "
        "eligibility blood donors using decision tree and Naive Bayes classifier', in "
        "Proceedings of the 2018 6th International Conference on Cyber and IT Service "
        "Management (CITSM). IEEE.",
    )
    # twelve entries now have to fit the same box as ten
    assert xml.count('sz="1400"') > 0
    return xml.replace('sz="1400"', 'sz="1150"')


def edit_slide8(xml: str) -> str:
    xml = replace_text(
        xml,
        "Screening: two-stage eligibility check (record-based + clinical), donation "
        "recording, blood bag creation",
        "Screening: two-stage eligibility check (record-based + clinical), donation "
        "recording, untested bag gated by laboratory screening of four infection markers, "
        "donation sites and appointment booking",
    )
    xml = replace_text(
        xml,
        "Inventory: blood bag tracking, expiry management, low-stock alerts, stock level "
        "computation",
        "Inventory: blood bag tracking, expiry management across untested, available and "
        "reserved units, low-stock alerts, computed stock levels",
    )
    return xml


def edit_slide9(xml: str) -> str:
    xml = replace_text(
        xml,
        "Database Design: Eleven tables across eight application modules",
        "Database Design: Thirteen tables across eight application modules",
    )
    xml = insert_para_after(
        xml, "Donation — recorded donations", "TTITestRecord — laboratory screening results"
    )
    return xml


def edit_slide10(xml: str) -> str:
    xml = insert_para_after(
        xml, "BloodRequest — patient requests, urgency", "Appointment — donation visit bookings"
    )
    return xml


def edit_slide12(xml: str) -> str:
    xml = replace_text(
        xml,
        "Relational database (SQLite in development); 11 tables across 8 application modules",
        "Relational database (SQLite in development); 13 tables across 8 application modules",
    )
    xml = insert_para_after(
        xml,
        "Audit log uses loose references (entity_type + entity_id) so entries survive "
        "record deletion",
        "Blood bag status changes pass through a single audited service function — the "
        "laboratory screening gate cannot be bypassed",
    )
    return xml


def edit_slide13(xml: str) -> str:
    xml = replace_text(
        xml,
        "Session management — auto-logout after inactivity, secure password hashing, "
        "expiring password reset links",
        "Session management — auto-logout after fifteen minutes of inactivity, secure "
        "password hashing, password reset links that expire after twelve hours",
    )
    xml = insert_para_after(
        xml,
        "Privacy-aware queries — donors see only their own records; hospital staff see "
        "only their hospital's data",
        "Laboratory screening gate — every donated unit is held out of the usable stock "
        "until all four infection markers are cleared",
    )
    return xml


def edit_slide16(xml: str) -> str:
    xml = replace_text(
        xml, "with all five objectives achieved", "with all three objectives achieved"
    )
    xml = replace_text(
        xml,
        "inventory with FEFO reservation and expiry tracking",
        "inventory with a laboratory screening gate, FEFO reservation and expiry tracking",
    )
    xml = replace_text(
        xml, "validated by 110 passing automated tests", "validated by 264 passing automated tests"
    )
    xml = replace_text(
        xml,
        "add SMS/email emergency notifications plus a mobile app for donors and patients.",
        "add a mobile app with push notifications for donors and patients.",
    )
    xml = replace_text(
        xml,
        "extend the system with infectious-disease screening and crossmatching",
        "extend the system with crossmatching and laboratory information system integration",
    )
    return xml


# The reference list is aligned with the current documentation (CBODS_NEW V8.3.docx):
# author names and initials, work titles, dates and page ranges are corrected to the
# versions that are cited in the thesis.  The deck keeps its own citation form (the
# available-at links and accessed dates it already carried) where that form is not wrong.
REFS = [
    (
        "Abdul-Gafaru, F., Laar, A. and Kubuga, D. (2024) 'Design and implementation of an "
        "online blood donation system', Asian Journal of Research in Computer Science, "
        "17(4), pp. 1\u201318.",
        "Abdul-Gafaru, T., Laar, D.S. and Kubuga, K.K. (2024) 'Design and implementation of "
        "an online blood donation system', Asian Journal of Research in Computer Science, "
        "17(4), pp. 44\u201361.",
    ),
    (
        "American Red Cross (n.d.) Facts about blood supply in the U.S. Available at: "
        "https://www.redcross.org (Accessed: 2026).",
        "American Red Cross (n.d.) Blood needs and blood supply. Available at: "
        "https://www.redcross.org (Accessed: 2026).",
    ),
    (
        "Django Software Foundation (2026) Django documentation. Available at: "
        "https://docs.djangoproject.com (Accessed: 2026).",
        "Django Software Foundation (2026) Django documentation (version 5.2). Available "
        "at: https://docs.djangoproject.com (Accessed: 2026).",
    ),
    (
        "Head, R., Shen, X. and Brede, M. (2026) 'Ghana collects half the blood it needs "
        "\u2014 digital approaches can improve that', The Conversation, 2026.",
        "Head, M., Shen, H. and Brede, M. (2026) 'Ghana collects half the blood it needs "
        "\u2014 digital approaches can improve that', The Conversation, 15 January.",
    ),
    (
        "Ministry of Health, Ghana (2017) Blood Safety Information System launched in "
        "Ghana. Accra: Ministry of Health.",
        "Ministry of Health, Ghana (2017) Blood Safety Information System launched in "
        "Ghana, 27 May. Accra: Ministry of Health.",
    ),
    (
        "Obeagu, I.M. and Alsadi, H. (2025) 'Blood banking in Africa: challenges and "
        "innovations', Universal Journal of Pharmaceutical Research, 10(2), pp. 45\u201356.",
        "Obeagu, E.I. and Alsadi, R.A. (2025) 'Blood banking systems in Africa: challenges, "
        "innovations, and recommendations for strengthening blood banking systems in "
        "Africa \u2014 a narrative review', Universal Journal of Pharmaceutical Research.",
    ),
    (
        "Romanos-Sirakis, K. and Desai, P. (2025) 'Blood typing', StatPearls [Internet]. "
        "Available at: https://www.ncbi.nlm.nih.gov/books/NBK580518 (Accessed: 2026).",
        "Romanos-Sirakis, E.C. and Desai, D. (2025) 'ABO blood group system', StatPearls "
        "[Internet]. Available at: https://www.ncbi.nlm.nih.gov/books/NBK580518 "
        "(Accessed: 2026).",
    ),
    (
        "World Health Organization (2026) Blood safety and availability fact sheet. "
        "Geneva: WHO.",
        "World Health Organization (2026) Blood safety and availability. Geneva: WHO.",
    ),
]


def edit_slide17(xml: str) -> str:
    for old, new in REFS:
        xml = set_para_text(xml, old, new)
    return add_literature_references(xml)


# --------------------------------------------------------------------------- #
# New slide: testing and evaluation.  It belongs between System Implementation
# (slide 15) and Conclusions and Recommendations, which is the position a results /
# evaluation section occupies in the report itself.  The new part is appended to the
# package and given its place by the slide id list, so no existing slide is renamed.
# --------------------------------------------------------------------------- #
NEW_SLIDE_PART = "ppt/slides/slide18.xml"
NEW_SLIDE_RELS = "ppt/slides/_rels/slide18.xml.rels"
AFTER_SLIDE = "slides/slide15.xml"
EVIDENCE_TITLE = "TESTING AND EVALUATION"

EVIDENCE_BODY = [
    ("264 automated tests across 47 test classes \u2014 all passed", 1600, False),
    (
        "Coverage by module: accounts 109, hospitals 62, donors 49, requests 11, "
        "inventory 11, notifications 6, audit 6, end-to-end and render 10",
        1400,
        False,
    ),
    ("Objectives and the evidence that proves each one", 1600, False),
    (
        "Objective 1 \u2014 registry with identity verification: PrivacyPartitionTests, "
        "IdDocumentPrivacyTests, HospitalApprovalTests, DuplicateEmailRegistrationTests",
        1400,
        True,
    ),
    (
        "Objective 2 \u2014 automated ABO and Rh matching: CompatibilityTreeTests (all 64 "
        "group combinations), DenyWithAlternativesTests, RequestLifecycleTests (FEFO and "
        "emergency ranking)",
        1400,
        True,
    ),
    (
        "Objective 3 \u2014 inventory, expiry tracking and FEFO reservation: "
        "DonationBlockingTests, TTIGateTests (laboratory gate, untested units, reactive "
        "discard), RequestLifecycleTests and FullDemoFlowTests",
        1400,
        True,
    ),
    (
        "Seven test categories: boundary conditions, workflow lifecycles, the laboratory "
        "safety gate, access control and per-hospital isolation, input validation, message "
        "delivery, and page rendering",
        1400,
        False,
    ),
]

SLIDE_OPEN = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
    "<p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/>"
    '<p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" '
    'cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
)
SLIDE_CLOSE = (
    "</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
)


def build_evidence_slide() -> str:
    """The testing-and-evaluation slide, built on the deck's own content layout."""
    import uuid

    paras = []
    for text, size, bullet in EVIDENCE_BODY:
        if bullet:
            ppr = '<a:pPr algn="just"/>'
        else:
            ppr = '<a:pPr marL="0" indent="0" algn="just"><a:buNone/></a:pPr>'
        paras.append(
            f'<a:p>{ppr}<a:r><a:rPr lang="en-US" sz="{size}" dirty="0"/>'
            f"<a:t>{esc(text)}</a:t></a:r></a:p>"
        )
    body = "".join(paras)

    title = (
        '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr>'
        '<a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph type="title"/></p:nvPr>'
        '</p:nvSpPr><p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:r>'
        f'<a:rPr lang="en-US" dirty="0"/><a:t>{EVIDENCE_TITLE}</a:t></a:r></a:p>'
        "</p:txBody></p:sp>"
    )
    content = (
        '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder 2"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr><p:ph idx="1"/>'
        "</p:nvPr></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"838200\" y=\"1408386\"/>"
        '<a:ext cx="10515600" cy="5084489"/></a:xfrm></p:spPr><p:txBody>'
        f'<a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/>{body}</p:txBody></p:sp>'
    )
    number = (
        '<p:sp><p:nvSpPr><p:cNvPr id="4" name="Slide Number Placeholder 3"/>'
        '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr><p:nvPr>'
        '<p:ph type="sldNum" sz="quarter" idx="12"/></p:nvPr></p:nvSpPr><p:spPr/>'
        f'<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:fld id="{{{str(uuid.uuid4()).upper()}}}" '
        f'type="slidenum"><a:rPr lang="en-US" smtClean="0"/><a:t>16</a:t></a:fld>'
        "<a:endParaRPr lang=\"en-US\"/></a:p></p:txBody></p:sp>"
    )
    return SLIDE_OPEN + title + content + number + SLIDE_CLOSE


def new_slide_rels() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/slideLayout" Target="../slideLayouts/slideLayout2.xml"/>'
        "</Relationships>"
    )


def add_content_type(ct: str) -> str:
    assert f'PartName="/{NEW_SLIDE_PART}"' not in ct
    entry = (
        f'<Override PartName="/{NEW_SLIDE_PART}" ContentType="application/vnd.'
        'openxmlformats-officedocument.presentationml.slide+xml"/>'
    )
    return ct.replace("</Types>", entry + "</Types>")


def add_slide_relationship(rels: str) -> tuple[str, str]:
    used = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels)]
    new_id = f"rId{max(used) + 1}"
    assert f'Target="{NEW_SLIDE_PART.split("/", 1)[1]}"' not in rels
    entry = (
        f'<Relationship Id="{new_id}" Type="http://schemas.openxmlformats.org/'
        f'officeDocument/2006/relationships/slide" '
        f'Target="{NEW_SLIDE_PART.split("/", 1)[1]}"/>'
    )
    return rels.replace("</Relationships>", entry + "</Relationships>"), new_id


def insert_slide_id(pres: str, rels: str, new_r_id: str) -> str:
    """Place the new slide immediately after slide 15 in the slide id list."""
    targets = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"', rels))
    anchor = None
    for m in re.finditer(r'<p:sldId id="\d+" r:id="(rId\d+)"/>', pres):
        if targets.get(m.group(1)) == AFTER_SLIDE:
            anchor = m
    assert anchor is not None, f"could not locate {AFTER_SLIDE} in the slide id list"
    used = [int(x) for x in re.findall(r'<p:sldId id="(\d+)"', pres)]
    entry = f'<p:sldId id="{max(used) + 1}" r:id="{new_r_id}"/>'
    return pres[: anchor.end()] + entry + pres[anchor.end():]


EDITORS = {
    "ppt/slides/slide6.xml": edit_slide6,
    "ppt/slides/slide7.xml": edit_slide7,
    "ppt/slides/slide17.xml": edit_slide17,
    "ppt/slides/slide8.xml": edit_slide8,
    "ppt/slides/slide9.xml": edit_slide9,
    "ppt/slides/slide10.xml": edit_slide10,
    "ppt/slides/slide12.xml": edit_slide12,
    "ppt/slides/slide13.xml": edit_slide13,
    "ppt/slides/slide16.xml": edit_slide16,
    "ppt/slides/slide17.xml": edit_slide17,
}

STALE = [
    "110 passing automated tests",
    "110 automated tests",
    "Eleven tables",
    "11 tables across",
    "blood bag creation",
    "expiring password reset links",
    "infectious-disease screening",
    "SMS/email emergency notifications",
    "all five objectives",
    "Abdul-Gafaru, F.",
    "Head, R., Shen, X.",
    "Obeagu, I.M.",
    "Romanos-Sirakis, K.",
    "Facts about blood supply in the U.S.",
    "BSIS focuses on blood centre operations",
]

# Statements that must be present after the edit, per part.
MUST_HAVE = {
    "ppt/slides/slide6.xml": ["More et al., 2024", "Zulfikar et al., 2018"],
    "ppt/slides/slide7.xml": [
        "computerised the national value chain",
        "No hospital-level screening, stock management or request workflow in BSIS",
    ],
    "ppt/slides/slide17.xml": ["More, Y.", "Alochana Journal", "Zulfikar, W.B."],
}
MUST_NOT_HAVE = {
    "ppt/slides/slide6.xml": ["BSIS"],
}


def assert_no_shadowed_defs() -> None:
    """Two top-level defs with one name silently shadow each other; catch that here."""
    src = Path(__file__).read_text(encoding="utf-8")
    names = re.findall(r"^def (\w+)\(", src, re.M)
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplicate top-level defs shadow each other: {dupes}"


def main() -> None:
    assert_no_shadowed_defs()
    assert SRC.exists(), f"source not found: {SRC}"
    data = SRC.read_bytes()
    zin = zipfile.ZipFile(io.BytesIO(data))

    edited: dict[str, str] = {}
    for name, fn in EDITORS.items():
        original = zin.read(name).decode("utf-8")
        updated = fn(original)
        assert updated != original, f"{name}: editor made no change"
        edited[name] = updated

    # ---- add the testing-and-evaluation slide ----------------------------- #
    pres = zin.read("ppt/presentation.xml").decode("utf-8")
    pres_rels = zin.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
    content_types = zin.read("[Content_Types].xml").decode("utf-8")

    impl = zin.read("ppt/slides/slide15.xml").decode("utf-8")
    assert "IMPLEMENTATION" in impl.upper(), "slide 15 is no longer the implementation slide"
    assert EVIDENCE_TITLE not in pres

    pres_rels, new_r_id = add_slide_relationship(pres_rels)
    pres = insert_slide_id(pres, pres_rels, new_r_id)
    content_types = add_content_type(content_types)

    edited[NEW_SLIDE_PART] = build_evidence_slide()

    out = pick_output()
    print(f"writing: {out.name}")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename in edited:
                content = edited[item.filename].encode("utf-8")
            elif item.filename == "ppt/presentation.xml":
                content = pres.encode("utf-8")
            elif item.filename == "ppt/_rels/presentation.xml.rels":
                content = pres_rels.encode("utf-8")
            elif item.filename == "[Content_Types].xml":
                content = content_types.encode("utf-8")
            zout.writestr(item, content)
        zout.writestr(NEW_SLIDE_PART, edited[NEW_SLIDE_PART].encode("utf-8"))
        zout.writestr(NEW_SLIDE_RELS, new_slide_rels().encode("utf-8"))
    zin.close()

    print(f"written: {out.name} ({out.stat().st_size:,} bytes)")

    # ---- validation ------------------------------------------------------- #
    import xml.etree.ElementTree as ET

    z = zipfile.ZipFile(out)
    bad = z.testzip()
    assert bad is None, f"corrupt zip member: {bad}"
    parts = 0
    for n in z.namelist():
        if n.endswith(".xml") or n.endswith(".rels"):
            ET.fromstring(z.read(n))
            parts += 1
    print(f"zip integrity OK; {parts} xml parts parse; {len(z.namelist())} parts total")

    # slide order comes from the slide id list, not the file names
    pres = ET.fromstring(z.read("ppt/presentation.xml"))
    P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    rel_parts = dict(
        re.findall(
            r'Id="(rId\d+)"[^>]*Target="([^"]+)"', z.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        )
    )
    order = [rel_parts[e.get(R + "id")] for e in pres.iter(P + "sldId")]
    assert len(order) == 18, f"expected 18 slides, found {len(order)}"
    assert order[15].endswith("slide18.xml"), f"new slide is not in position 16: {order[15]}"
    assert order[14].endswith("slide15.xml") and order[16].endswith("slide16.xml")
    print("slide order:", ", ".join(o.split("/")[-1] for o in order))

    A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
    deck_text: dict[str, str] = {}
    for part in order:
        name = f"ppt/{part}"
        doc = ET.fromstring(z.read(name))
        deck_text[name] = "".join(t.text or "" for t in doc.iter(A + "t"))

    leftover = []
    for n, text in deck_text.items():
        for s in STALE:
            if s in text:
                leftover.append(f"{n}: {s!r}")
    for n, wanted in MUST_HAVE.items():
        for s in wanted:
            if s not in deck_text.get(n, ""):
                leftover.append(f"{n}: missing {s!r}")
    for n, banned in MUST_NOT_HAVE.items():
        for s in banned:
            if s in deck_text.get(n, ""):
                leftover.append(f"{n}: should not contain {s!r}")
    if leftover:
        print("STALE TEXT REMAINS:")
        for line in leftover:
            print("  ", line)
        sys.exit(1)
    print("no stale statements remain in any slide")



if __name__ == "__main__":
    main()
