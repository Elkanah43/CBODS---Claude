"""Build the TTI laboratory-gate rewrites (UNTESTED -> AVAILABLE flow) for
CBODS_NEW V7.2.docx, covering every passage in Chapters 3 and 4 that describes
donation recording or blood bag statuses.

Emits, from one source of truth:
  * TTI_GATE_REWRITES.docx - Word document whose replacement paragraphs match
    the thesis body (Times New Roman 12 pt, justified), ready to paste.
  * TTI_gate_rewrites.md   - the same text as markdown.

Read-only with respect to the master document.
"""
from __future__ import annotations

import html
import io
import zipfile
from pathlib import Path

OUT_DOCX = Path("TTI_GATE_REWRITES.docx")
OUT_MD = Path("TTI_gate_rewrites.md")

SECTIONS = [
    {
        "title": "How to use this rewrite set",
        "lead": "This document rewrites every passage in Chapters Three and Four that describes donation "
                "recording or blood bag statuses, so that the laboratory screening gate - every bag is born "
                "untested and becomes available only after all four TTI markers are non-reactive - is stated "
                "consistently from the requirements through the data design, the workflow diagrams and the "
                "implementation narrative. Each item names the passage and quotes the sentence to locate with "
                "Find; replacement paragraphs are set like the thesis body. If you have already applied "
                "sections 4-6 of CBODS_CORRECTIONS.docx, its donation-recording, laboratory-screening, "
                "inventory-management, Phase 2 and Phase 3 rewrites are the same text as items A1, A2, A3, E1 "
                "and E2 here - apply those once, and use the remaining items here for the passages that "
                "document did not cover.",
        "items": [],
    },
    {
        "title": "A.  Section 3.2.3 - the functional requirements",
        "lead": "The requirements currently describe a bag that becomes available the moment a donation is "
                "recorded, and a status list with no untested state. Three requirements change and one is "
                "new.",
        "items": [
            {
                "where": "Section 3.2.3, replace the whole \"Donation recording\" requirement.",
                "find": None,
                "replace": [
                    "Donation recording: Hospital staff shall be able to record a completed donation for an "
                    "eligible donor. The system shall enforce eligibility at the time of recording, so that a "
                    "donation cannot be recorded for a donor whose registration is not approved, who has no "
                    "recent eligible screening, or who has not yet waited the required interval. Each "
                    "recorded donation shall create a corresponding blood bag in the hospital's inventory "
                    "with a computed expiry date, and shall open a laboratory screening record for that "
                    "donation. The new bag shall be created in the untested state, and shall not be counted "
                    "in stock, offered to a request or issued until the laboratory has recorded a "
                    "non-reactive result for every marker of the transfusion-transmissible infection panel "
                    "(HIV, hepatitis B, hepatitis C and syphilis)."
                ],
            },
            {
                "where": "Section 3.2.3 - new requirement paragraph, inserted immediately after \"Donation "
                         "recording\".",
                "find": None,
                "insert": True,
                "replace": [
                    "Laboratory screening: Hospital staff shall be able to enter the laboratory results for a "
                    "recorded donation, one result for each marker of the transfusion-transmissible "
                    "infection panel - HIV, hepatitis B, hepatitis C and syphilis. All four results shall be "
                    "required before the screening is treated as complete, and an incomplete screening shall "
                    "neither release nor discard the unit. The outcome of the screening shall gate the blood "
                    "bag: the bag shall move from untested to available only when every result is "
                    "non-reactive, and shall be discarded when any result is reactive, with the reactive "
                    "markers recorded as the reason and the donor notified and advised to seek counselling "
                    "and confirmatory testing. A screening that has been completed shall not be entered a "
                    "second time, and a unit that reaches its expiry date before the laboratory clears it "
                    "shall be marked expired rather than released."
                ],
            },
            {
                "where": "Section 3.2.3, replace the whole \"Inventory management\" requirement.",
                "find": None,
                "replace": [
                    "Inventory management: The system shall maintain, for each registered hospital, a record "
                    "of every blood bag and its status. The possible statuses of a bag are untested, "
                    "available, reserved, issued, expired and discarded, and a bag that has just been "
                    "recorded begins as untested. The system shall calculate stock levels from the available "
                    "bags rather than storing a separate counter, so that the displayed stock is always "
                    "consistent with the underlying records; units awaiting the laboratory shall be visible "
                    "to hospital staff but excluded from the stock figures and unavailable for reservation. "
                    "It shall identify bags that are close to their expiry date, mark bags that have passed "
                    "their expiry date - including bags still awaiting the laboratory - and notify hospital "
                    "staff when the available stock of any blood group falls below a defined threshold."
                ],
            },
            {
                "where": "Section 3.2.3, \"Blood requests and matching\" requirement - add this sentence at "
                         "the end of the requirement.",
                "find": "Where an emergency request cannot be met from available stock, the system shall "
                        "send an urgent broadcast notification to the compatible donors registered in the "
                        "hospital's city.",
                "replace": [
                    "Where an emergency request cannot be met from available stock, the system shall send an "
                    "urgent broadcast notification to the compatible donors registered in the hospital's "
                    "city. Only bags that have passed the laboratory screening gate shall be eligible for "
                    "reservation; a unit that is still untested shall not appear in the stock a request can "
                    "draw on."
                ],
            },
            {
                "where": "Section 3.2.3 (non-functional requirements), \"Reliability\" - add this sentence at "
                         "the end.",
                "find": "The system shall prevent a bag from being reserved or issued twice, even when two "
                        "users act at the same time.",
                "replace": [
                    "The system shall prevent a bag from being reserved or issued twice, even when two users "
                    "act at the same time. The release of a screened unit into the available pool, the "
                    "discarding of a reactive unit and the expiry of a past-date unit shall each be applied "
                    "through a single audited code path, so that a status change and its audit entry cannot "
                    "be recorded separately."
                ],
            },
        ],
    },
    {
        "title": "B.  Section 3.3.2 - the data design",
        "lead": "The database section counts eleven tables, describes the bag statuses without the untested "
                "state, and holds no laboratory screening record. The table count, the BloodBag description "
                "and the design-decision paragraph all change, and two sentences are added.",
        "items": [
            {
                "where": "Section 3.3.2, opening sentence of the database description.",
                "find": "The database that supports CBODS is a relational database containing eleven tables, "
                        "and its structure follows directly from the workflows described in the functional "
                        "requirements.",
                "replace": [
                    "The database that supports CBODS is a relational database containing thirteen tables, "
                    "and its structure follows directly from the workflows described in the functional "
                    "requirements."
                ],
            },
            {
                "where": "Section 3.3.2, in the paragraph on donor management - replace the sentence "
                         "describing the BloodBag table.",
                "find": "The BloodBag table represents a single unit of donated blood and stores its blood "
                        "group, volume, collection date, expiry date (computed as the collection date plus "
                        "thirty-five days), current status (available, reserved, issued, expired or "
                        "discarded), the donation from which it was created, and if the bag has been "
                        "allocated the blood request for which it is reserved.",
                "replace": [
                    "The BloodBag table represents a single unit of donated blood and stores its blood "
                    "group, volume, collection date, expiry date (computed as the collection date plus "
                    "thirty-five days), current status (untested, available, reserved, issued, expired or "
                    "discarded), the donation from which it was created, and if the bag has been allocated "
                    "the blood request for which it is reserved. Every bag is created in the untested state, "
                    "and it is the laboratory screening record described below that decides when it may "
                    "enter the available pool."
                ],
            },
            {
                "where": "Section 3.3.2 - two new sentences, inserted at the end of the same paragraph (after "
                         "the OrganDonationRequest description).",
                "find": None,
                "insert": True,
                "replace": [
                    "The laboratory screening of each donation is held in its own table, linked one-to-one "
                    "to the donation, which stores one result for each marker of the infection panel, the "
                    "staff member who entered the results, the time of entry and the reason recorded when a "
                    "unit is discarded. The record is kept after the decision, so that the reason a unit was "
                    "discarded survives alongside the audit trail. An Appointment table records a donor's "
                    "request to donate at a chosen hospital on a proposed date, together with the donor's "
                    "note, the hospital's decision and note, and the time of the decision."
                ],
            },
            {
                "where": "Section 3.3.2, the paragraph on design decisions - add this sentence at the end.",
                "find": "This design was chosen deliberately, because in a real hospital two staff members "
                        "could act on the same request or the same stock at almost the same moment, and the "
                        "system must behave correctly in that situation.",
                "replace": [
                    "This design was chosen deliberately, because in a real hospital two staff members could "
                    "act on the same request or the same stock at almost the same moment, and the system "
                    "must behave correctly in that situation. A further decision concerns the safety gate: "
                    "every change to a bag's status passes through a single service function, so that a "
                    "unit cannot reach the available, reserved or discarded state without the change and its "
                    "reason being written to the audit log at the same moment."
                ],
            },
        ],
    },
    {
        "title": "C.  Section 3.3.3 - the matching component and the workflow diagrams",
        "lead": "The request-lifecycle narrative assumes the pool it draws from is the available stock; each "
                "passage below is tightened so that the pool is explicitly the set of laboratory-cleared "
                "units.",
        "items": [
            {
                "where": "Section 3.3.3, the paragraph describing the matching component - add this sentence "
                         "at the end.",
                "find": "For emergency requests, donors who can donate immediately are ranked first, because "
                        "the need is immediate.",
                "replace": [
                    "For emergency requests, donors who can donate immediately are ranked first, because the "
                    "need is immediate. The pool of bags against which the component matches is the set of "
                    "units that have passed the laboratory screening gate; a unit still awaiting the "
                    "laboratory is invisible to the matching process, however recently it was collected."
                ],
            },
            {
                "where": "Section 3.3.3, the sequence-diagram walkthrough (acceptance transaction) - replace "
                         "the quoted clause.",
                "find": "Within this transaction, the required number of compatible bags are located in "
                        "first-expiry-first-out order, each bag is linked to the request and its status is "
                        "changed from available to reserved, and the request status is updated to accepted.",
                "replace": [
                    "Within this transaction, the required number of compatible bags are located in "
                    "first-expiry-first-out order among the units that have passed the laboratory screening "
                    "gate, each bag is linked to the request and its status is changed from available to "
                    "reserved, and the request status is updated to accepted."
                ],
            },
            {
                "where": "Section 3.3.3, the Figure 3.6 flowchart description - replace the quoted clause.",
                "find": "the system enters an atomic transaction that locks the request row, locates "
                        "compatible bags in first-expiry-first-out order, reserves them and updates the "
                        "request status to accepted",
                "replace": [
                    "the system enters an atomic transaction that locks the request row, locates compatible "
                    "bags in first-expiry-first-out order among the units cleared by the laboratory "
                    "screening gate, reserves them and updates the request status to accepted"
                ],
            },
            {
                "where": "Section 3.3.3, the Figure 3.5 data-flow description - replace the quoted sentence.",
                "find": "When a donation is completed, the Donation Recording and Inventory Management "
                        "process creates a Blood Bag Inventory record linked to the donor and the hospital.",
                "replace": [
                    "When a donation is completed, the Donation Recording and Inventory Management process "
                    "creates a Blood Bag Inventory record linked to the donor and the hospital in the "
                    "untested state, together with a laboratory screening record; the unit joins the "
                    "available stock in that store only once the screening results have been entered and "
                    "every marker is non-reactive, and a reactive unit is discarded instead."
                ],
                "note": "If Figure 3.5 is redrawn, add a Laboratory Screening process between Donation "
                        "Recording and the inventory store; the wording above also stands against the "
                        "present figure.",
            },
        ],
    },
    {
        "title": "D.  Section 3.3.6 and the Chapter Three summary",
        "lead": "The audit-trail requirement should name the gate explicitly, and the chapter summary should "
                "list it among the safety measures.",
        "items": [
            {
                "where": "Section 3.3.6, \"Audit trail\" - replace the quoted sentence.",
                "find": "This includes the approval and rejection of donors, the creation and status changes "
                        "of blood bags, the acceptance, rejection and fulfilment of requests, and the "
                        "progress of organ donation requests.",
                "replace": [
                    "This includes the approval and rejection of donors, the creation of blood bags in the "
                    "untested state and every subsequent change of their status, the entry of laboratory "
                    "screening results and the release or discard of the units they decide, the acceptance, "
                    "rejection and fulfilment of requests, and the progress of organ donation requests."
                ],
            },
            {
                "where": "Chapter Three summary, the sentence listing the security measures - replace the "
                         "quoted ending.",
                "find": "centred on role-based access control, the restricted handling of identity documents, "
                        "privacy-aware queries, session and password security, and a complete audit trail.",
                "replace": [
                    "centred on role-based access control, the restricted handling of identity documents, "
                    "privacy-aware queries, session and password security, the laboratory screening gate "
                    "that holds every donated unit out of the usable stock until it is cleared, and a "
                    "complete audit trail."
                ],
            },
        ],
    },
    {
        "title": "E.  Chapter Four - the implementation narrative",
        "lead": "Phase 2 ends with a bag simply appearing in inventory, Phase 3 expires only \"available\" "
                "bags, and both test descriptions show the bag becoming available at the moment of recording. "
                "Five passages change.",
        "items": [
            {
                "where": "Section 4.1.2, replace the whole Phase 2 paragraph.",
                "find": None,
                "replace": [
                    "Phase 2: Donor Screening and Donation Recording. The second phase implemented the "
                    "two-stage screening process and the recording of donations. When hospital staff select "
                    "an approved donor for screening, the system first runs the stage-one eligibility check, "
                    "which evaluates the donor's age, weight and the interval since the last donation "
                    "against the thresholds configured in the application (see Table 3.2 in Chapter Three). "
                    "The stage-one check returns one of three outcomes: eligible, temporarily deferred, or "
                    "permanently ineligible. Hospital staff then enter the donor's haemoglobin level and "
                    "blood pressure readings for the stage-two clinical screening. The combined outcome of "
                    "both stages is recorded as a screening record, and the donor is notified. Recording a "
                    "donation enforces eligibility at the point of action: the system checks that the "
                    "donor's registration is approved, that a recent screening exists with an eligible "
                    "outcome, and that the required interval since the last donation has elapsed. A "
                    "successful recording creates a donation record and a corresponding blood bag in the "
                    "hospital's inventory, with the expiry date computed as the collection date plus the "
                    "configured shelf life of thirty-five days. The new bag is created in the untested "
                    "state, and the laboratory screening record for the donation is opened at the same "
                    "moment, so that no unit can enter the stock pool before the laboratory has cleared it. "
                    "The member of staff who recorded the donation is taken straight to the laboratory "
                    "screening queue, which lists the hospital's donations awaiting screening oldest first. "
                    "Entering the four results - HIV, hepatitis B, hepatitis C and syphilis - completes the "
                    "screening: when every result is non-reactive the bag moves from untested to available "
                    "and enters the stock pool, and when any result is reactive the bag is discarded, with "
                    "the reactive markers recorded as the reason, and the donor is notified and advised to "
                    "seek counselling and confirmatory testing. While the screening is incomplete the bag is "
                    "visible in the hospital's inventory but is excluded from the stock figures and cannot "
                    "be reserved, and a unit that reaches its expiry date before the laboratory clears it is "
                    "marked expired instead of being released."
                ],
            },
            {
                "where": "Section 4.1.2, replace the whole Phase 3 paragraph.",
                "find": None,
                "replace": [
                    "Phase 3: Blood Bag Inventory and Expiry Tracking. The third phase added the inventory "
                    "dashboard and the expiry tracking mechanism. The inventory is displayed on a "
                    "per-hospital basis, with stock levels for each blood group computed from the available "
                    "bags rather than stored as a separate counter. This design ensures that the displayed "
                    "stock is always consistent with the underlying records. Units awaiting laboratory "
                    "screening are shown separately from the available stock, so that hospital staff can see "
                    "what is still in the laboratory without it being counted as usable blood. The system "
                    "identifies bags that are within seven days of their expiry date and highlights them for "
                    "attention. A daily management command scans every bag that has not yet reached a final "
                    "state - untested, available and reserved alike - and changes the status of any bag "
                    "whose expiry date has passed to expired, recording the event in the audit log and "
                    "sending a low-stock notification to the hospital's staff when the available stock of "
                    "any blood group falls below the configured threshold."
                ],
            },
            {
                "where": "Section 4.1.2, Phase 4 - add this sentence at the end of the paragraph.",
                "find": "When an emergency request cannot be met from available stock, the system sends an "
                        "urgent broadcast notification to compatible donors registered in the hospital's "
                        "city, and presents hospital staff with a ranked list of compatible donors, "
                        "rioritizing those who can donate immediately.",
                "replace": [
                    "When an emergency request cannot be met from available stock, the system sends an "
                    "urgent broadcast notification to compatible donors registered in the hospital's city, "
                    "and presents hospital staff with a ranked list of compatible donors, prioritizing those "
                    "who can donate immediately. Only bags that have cleared laboratory screening take part "
                    "in the reservation that follows; the matching and reservation code never sees a unit "
                    "that is still untested."
                ],
            },
            {
                "where": "Section 4.1.3, inside the workflow-tests paragraph (the end-to-end sentence) - "
                         "replace the quoted clause.",
                "find": "staff record a donation, which creates an available blood bag;",
                "replace": [
                    "staff record a donation, which creates an untested blood bag, and enter laboratory "
                    "screening results that clear the bag into the available pool;"
                ],
            },
            {
                "where": "Section 4.2.2, the end-to-end walkthrough chain - replace the quoted chain.",
                "find": "donor registration -> administrator approval -> screening -> donation recording -> "
                        "patient blood request -> acceptance and reservation -> fulfilment and notification "
                        "-> emergency broadcast -> organ donation request -> hospital approval -> "
                        "administrator dashboard and audit log verification",
                "replace": [
                    "donor registration -> administrator approval -> screening -> donation recording -> "
                    "laboratory screening clears the unit -> patient blood request -> acceptance and "
                    "reservation -> fulfilment and notification -> emergency broadcast -> organ donation "
                    "request -> hospital approval -> administrator dashboard and audit log verification"
                ],
            },
            {
                "where": "Section 4.2.4, \"Consistency\" - add this sentence at the end.",
                "find": "The age of a donor is derived from the date of birth, and the interval since the "
                        "last donation is derived from the donation records, so no cached value can drift "
                        "out of step with the data it summarises.",
                "replace": [
                    "The age of a donor is derived from the date of birth, and the interval since the last "
                    "donation is derived from the donation records, so no cached value can drift out of step "
                    "with the data it summarises. The same discipline applies to the laboratory gate: an "
                    "untested unit is excluded from the stock computation by the same query that counts the "
                    "available bags, so a unit awaiting the laboratory can never appear as usable stock."
                ],
            },
        ],
    },
]


# --------------------------------------------------------------------------- #
# Markdown renderer
# --------------------------------------------------------------------------- #
def render_markdown() -> str:
    parts = [
        "# CBODS_NEW V7.2 - TTI laboratory gate rewrites (Chapters 3 and 4)",
        "",
        "Rewrites every passage describing donation recording or blood bag statuses so that the "
        "UNTESTED -> AVAILABLE flow is stated consistently: requirements (3.2.3), data design (3.3.2), "
        "workflow diagrams (3.3.3), security (3.3.6), the chapter summary, the phase narrative (4.1.2) and "
        "the test narrative (4.1.3, 4.2.2, 4.2.4). Nothing here has been written into "
        "`CBODS_NEW V7.2.docx`.",
        "",
        "Note: items A1, A2, A3, E1 and E2 are the same rewrites as sections 4-6 of "
        "`CBODS_CORRECTIONS.docx`; the other items here are additional passages that document did not "
        "cover.",
        "",
    ]
    for sec in SECTIONS:
        parts += [f"## {sec['title']}", "", sec["lead"], ""]
        for item in sec["items"]:
            parts += [f"**Where: {item['where']}**", ""]
            if item.get("find"):
                parts += [f"*Find:* {item['find']}", ""]
            if item.get("insert"):
                parts += ["*New sentences - insert at the position named above:*", ""]
            for i, para in enumerate(item["replace"]):
                label = "*Replacement text:* " if i == 0 else "*Continuation:* "
                parts += [label + para, ""]
            if item.get("note"):
                parts += [f"*Note:* {item['note']}", ""]
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


def quoted(text) -> str:
    return para(text, italic=True, size=22, color="444444", indent=340, space_after=120)


def render_docx() -> bytes:
    body = []
    body.append(para("CBODS_NEW V7.2 - TTI laboratory gate rewrites", bold=True, size=32,
                     space_after=120, keep_next=True))
    body.append(para("Donation recording and blood bag statuses, rewritten for the UNTESTED -> AVAILABLE "
                     "flow, consistently across Chapters Three and Four", italic=True, size=22,
                     color="555555", space_after=200))
    for sec in SECTIONS:
        body.append(para(sec["title"], bold=True, size=28, color="1F3864", space_after=80,
                         keep_next=True))
        body.append(para(sec["lead"], size=21, color="444444", justify=True, space_after=160))
        for item in sec["items"]:
            body.append(label(f"Where: {item['where']}"))
            if item.get("find"):
                body.append(label("Find:"))
                body.append(quoted(item["find"]))
                body.append(label("Replace with:"))
            if item.get("insert"):
                body.append(label("(new sentences - insert at the position named above)"))
            for p in item["replace"]:
                body.append(para(p, justify=True, space_after=200))
            if item.get("note"):
                body.append(label(f"Note: {item['note']}"))
                body.append(para("", space_after=80))
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
    n_items = sum(len(s["items"]) for s in SECTIONS)
    OUT_MD.write_text(render_markdown(), encoding="utf-8")
    OUT_DOCX.write_bytes(render_docx())
    print(f"{OUT_MD}  ({OUT_MD.stat().st_size} bytes)")
    print(f"{OUT_DOCX}  ({OUT_DOCX.stat().st_size} bytes)")
    print(f"{len(SECTIONS) - 1} sections, {n_items} rewrites")


if __name__ == "__main__":
    main()
