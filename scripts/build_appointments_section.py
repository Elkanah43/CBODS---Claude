"""Build the donor-appointment Key Features entry for Chapter Four of
CBODS_NEW V7.2.docx, written in the same style as the existing entries
(Figure 4.x caption, ALL-CAPS page title, one walkthrough paragraph).

Emits, from one source of truth:
  * APPOINTMENTS_SECTION.docx - Word document whose paragraphs match the
    thesis body (Times New Roman 12 pt, justified), ready to paste.
  * appointments_section.md   - the same text as markdown.

Read-only with respect to the master document.
"""
from __future__ import annotations

import html
import io
import zipfile
from pathlib import Path

OUT_DOCX = Path("APPOINTMENTS_SECTION.docx")
OUT_MD = Path("appointments_section.md")

FIGURE_NO = "4.10"
PAGE_TITLE = "WHERE TO DONATE (DONATION SITES AND APPOINTMENTS)"

FEATURE_PARAGRAPHS = [
    # Main walkthrough paragraph, in the voice of the other Key Features entries.
    "The donation sites directory is the page an approved donor uses to decide where to give "
    "blood. It lists the hospitals that are open to donations, and beside each hospital it shows "
    "the blood groups that hospital currently holds in available stock, with the groups that have "
    "fallen below the low-stock threshold flagged. The list is ordered so that it answers two "
    "questions at once: hospitals in the donor's own city are ranked first, and within that group "
    "the hospitals that are short of the donor's own blood group come first, carrying a badge that "
    "marks the need. A donor can therefore see both where they can go and where they would be most "
    "useful. Eligibility is not decided on this page: the directory is informational, and the "
    "standing eligibility rules are still applied by hospital staff at the time of screening.",

    "From the directory the donor can book a visit. The booking form asks for the day the donor "
    "proposes to come in and an optional note for the hospital, and it accepts only a date between "
    "today and sixty days ahead. A booking is refused unless the donor's registration has been "
    "approved, and a donor who already holds a pending booking at the same hospital is shown that "
    "booking instead of being offered a second one. When the booking is created, the staff of the "
    "chosen hospital are notified immediately, with the donor's name and blood group in the "
    "message, and the appointment enters a pending state that both sides can see.",

    "Hospital staff review bookings in their appointment inbox, which lists the hospital's "
    "appointments newest first with a count of those still pending. Staff either confirm a booking "
    "or decline it with a note, and the donor is notified of the decision either way; the "
    "confirmation message reminds the donor to bring their government identity document. A donor "
    "can cancel a booking that has not yet been decided, which closes the appointment and tells "
    "the hospital's staff. Every step of the workflow - the booking, the cancellation, the "
    "confirmation and the decline - is recorded in the audit log with the actor and the date, so "
    "the appointment record gives both sides a shared status instead of an untracked telephone "
    "call. The directory, the booking form, the donor's appointment list and the staff inbox are "
    "exercised by the appointment and donation-site tests described in Section 4.1.3 "
    "(DonationSitesTests and AppointmentTests).",
]

RELATED_EDITS = [
    {
        "where": "The List of Figures (front matter) - add this line after the Figure 4.9 entry.",
        "text": "Figure 4.10: Donation sites directory and appointment booking",
    },
    {
        "where": "Section 4.1.2, Phase 1 (or Phase 5) - one sentence recording when the feature was built, "
                 "so the phase narrative and the interface walkthrough agree.",
        "text": "The same phase added the donor-facing donation sites directory, from which an approved "
                "donor can book a donation appointment at a chosen hospital for staff to confirm or "
                "decline.",
    },
    {
        "where": "Section 4.1.3 - one sentence appended to the workflow-tests paragraph, so the test "
                 "narrative covers the feature shown in Figure 4.10.",
        "text": "The appointment tests book a visit from the donation sites directory, verify that an "
                "unapproved donor and a hidden hospital are refused, and confirm that hospital staff can "
                "confirm or decline the booking with the donor notified in each case.",
    },
]

HOW_TO = (
    "Insert this entry at the end of Section 4.2.3 (Key Features and Interface Implementation), "
    "immediately after the HOSPITAL REPORT entry and before the Performance Evaluation heading. "
    "Take a screenshot of the donation sites directory (signed in as an approved donor) for the "
    "figure. If you have already applied section 9 of CBODS_CORRECTIONS.docx, its interface "
    "paragraph is an earlier draft of the same entry - use this version instead, and keep its "
    "requirement and data-design paragraphs."
)


# --------------------------------------------------------------------------- #
# Markdown renderer
# --------------------------------------------------------------------------- #
def render_markdown() -> str:
    parts = [
        "# CBODS_NEW V7.2 - Key Features entry: donor appointments",
        "",
        "A new Section 4.2.3 entry in the style of the existing ones (Figure caption, ALL-CAPS page "
        "title, walkthrough paragraphs). Nothing here has been written into `CBODS_NEW V7.2.docx`.",
        "",
        f"**Placement:** {HOW_TO}",
        "",
        f"**Figure {FIGURE_NO}: Donation sites directory and appointment booking**",
        "",
        f"### {PAGE_TITLE}",
        "",
    ]
    for p in FEATURE_PARAGRAPHS:
        parts += [p, ""]
    parts += ["## Related one-line edits", ""]
    for e in RELATED_EDITS:
        parts += [f"**Where: {e['where']}**", "", e["text"], ""]
    return "\n".join(parts)


# --------------------------------------------------------------------------- #
# DOCX renderer (OOXML written directly, no third-party packages)
# --------------------------------------------------------------------------- #
def esc(text: str) -> str:
    return html.escape(text, quote=False)


def rpr(bold=False, italic=False, size=24, color=None, font="Times New Roman") -> str:
    r = f'<w:rFonts w:ascii="{font}" w:eastAsia="{font}" w:hAnsi="{font}" w:cs="{font}"/>'
    if bold:
        r += "<w:b/>"
    if italic:
        r += "<w:i/>"
    if color:
        r += f'<w:color w:val="{color}"/>'
    r += f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>'
    return f"<w:rPr>{r}</w:rPr>"


def para(text, *, bold=False, italic=False, size=24, color=None, font="Times New Roman",
         justify=False, indent=0, space_after=160, keep_next=False) -> str:
    ppr = "<w:pPr>"
    if keep_next:
        ppr += "<w:keepNext/>"
    ppr += f'<w:spacing w:after="{space_after}" w:line="276" w:lineRule="auto"/>'
    if indent:
        ppr += f'<w:ind w:left="{indent}"/>'
    if justify:
        ppr += '<w:jc w:val="both"/>'
    ppr += "</w:pPr>"
    props = rpr(bold, italic, size, color, font)
    runs = "".join(
        ("" if i == 0 else "<w:r><w:br/></w:r>")
        + f'<w:r>{props}<w:t xml:space="preserve">{esc(part)}</w:t></w:r>'
        for i, part in enumerate(text.split("\n"))
    )
    if not runs:
        runs = f"<w:r>{props}</w:r>"
    return f"<w:p>{ppr}{runs}</w:p>"


def label(text) -> str:
    return para(text, italic=True, size=19, color="666666", font="Calibri", space_after=80,
                keep_next=True)


def render_docx() -> bytes:
    body = []
    body.append(para("CBODS_NEW V7.2 - Key Features entry: donor appointments", bold=True, size=32,
                     space_after=120, keep_next=True))
    body.append(para("A new Section 4.2.3 entry in the style of the existing entries", italic=True,
                     size=22, color="555555", space_after=200))
    body.append(para(HOW_TO, size=21, color="333333", justify=True, space_after=240))

    body.append(label(f"Figure {FIGURE_NO}: Donation sites directory and appointment booking "
                      "(insert the screenshot here)"))
    body.append(para(PAGE_TITLE, bold=True, size=24, space_after=160, keep_next=True))
    for p in FEATURE_PARAGRAPHS:
        body.append(para(p, justify=True, space_after=200))

    body.append(para("Related one-line edits", bold=True, size=28, color="1F3864", space_after=80,
                     keep_next=True))
    for e in RELATED_EDITS:
        body.append(label(f"Where: {e['where']}"))
        body.append(para(e["text"], justify=True, space_after=200))
    return docx_bytes("".join(body))


def docx_bytes(body_xml: str) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body_xml}<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1418"/></w:sectPr></w:body>'
        "</w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def main() -> None:
    OUT_MD.write_text(render_markdown(), encoding="utf-8")
    OUT_DOCX.write_bytes(render_docx())
    print(f"{OUT_MD}  ({OUT_MD.stat().st_size} bytes)")
    print(f"{OUT_DOCX}  ({OUT_DOCX.stat().st_size} bytes)")
    print(f"{len(FEATURE_PARAGRAPHS)} feature paragraphs, {len(RELATED_EDITS)} related edits")


if __name__ == "__main__":
    main()
