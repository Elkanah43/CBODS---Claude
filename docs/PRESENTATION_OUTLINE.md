# CBODS — 10-Slide Presentation Outline

Companion to [PANEL_PREP.md](PANEL_PREP.md). Timed for a **10-minute talk**
(~1 minute per slide) plus Q&A. "On slide" is the minimum text the audience
sees; "Notes" is what you say. Slides 2, 7 and 10 are the cut list if the
chairman asks you to compress — cut in that order.

---

## Slide 1 — Title (0:30)

**On slide:**
- CBODS — Centralised Blood & Organ Donation System
- Your name · course · supervisor · date
- Tagline: *"From donor registration to a transfused unit — one audited system."*

**Notes:** Greet the panel, give your name and project title, then the tagline.
One breath, then move — the title slide earns you nothing; the next slide
earns attention.

---

## Slide 2 — The problem (1:00)

**On slide:**
- Blood shortages kill: mothers, children with malaria, trauma victims
- Coordination failures, not just shortages: the right group, at the right
  hospital, at the right hour
- Donors are willing — nothing tells them *where they are needed today*
- Records live on paper; audit means memory

**Notes:** Lead with stakes, then pivot fast from "not enough blood" to the
sharper problem — *coordination*. Ghana collects blood, but willingness and
need never meet through a system; they meet by phone. Say the last line
looking at the panel: paper records cannot be audited, and untracked blood is
unsafe blood. This sets up both your comparison slide and your TTI gate later.

---

## Slide 3 — What exists, and the gap (1:00)

**On slide:**
- **NBSG (nbs.gov.gh):** educates, publishes schedules, books one centre —
  final answers happen in person
- **BSIS (Jembi/CDC):** tracks units *inside* the blood service — registration
  → testing → processing → distribution
- **Nobody connects** donor ↔ hospital stock ↔ patient request
- CBODS = the missing connecting layer, *with* the lab gate modelled

**Notes:** This slide shows you did your literature review. One sentence per
system, then the gap in one line: NBSG is broadcast-first, BSIS is
back-office, and the demand side — patients — appears in neither. Close with
the positioning sentence from the prep doc: mobilisation, chain-of-custody,
and connection are three different jobs; CBODS does the third and borrows the
safety rules of the second.

---

## Slide 4 — What CBODS is (1:00)

**On slide:**
- Django 5 web platform · 8 apps · 12 models · server-rendered
- Four roles: Donor · Patient · Hospital staff · Admin
- Every consequential action: permission-checked → service-validated → audited
- Deliberately a monolith: correctness first, small error surface

**Notes:** Keep architecture to 20 seconds — panels care about decisions, not
diagrams. Justify the monolith before anyone asks: Django's auth, CSRF, admin
and migrations shrink the error surface, and server-rendered pages work well
on the low-end devices a Ghanaian hospital actually has. Name the pattern that
repeats through the system: the UI never has the final word — the service
layer re-checks everything.

---

## Slide 5 — The donor journey (1:00)

**On slide:**
- Register with government ID → admin approval → donor account
- "Where to donate": live hospital directory **ranked by scarcity**
- Book where *your* group is short; staff confirm in-app; donor notified
- Two-stage screening: stage 1 from records, stage 2 measured (Hb, BP)

**Notes:** Walk the happy path in donor order. Emphasise the one genuinely
novel bit: booking is steered by live stock, so donors land where blood is
scarcest — that inverts the usual "find any centre" model. On privacy, one
line: the ID scan is uploaded once, streamed only through an admin-gated
view — the media folder has no public route at all. Leave the audit point for
slide 8; don't spend it here.

---

## Slide 6 — The demand side: requests (1:00)

**On slide:**
- Patient requests blood: group, units, urgency (routine / urgent / emergency)
- ABO/Rh compatibility engine: exact data dict, enforced in services
- No match? → denial *with alternatives* → emergency donor broadcast
- Urgency changes strategy: emergencies chase donors who can give *today*

**Notes:** This is the slide no compared system has. Demonstrate depth with
one example: an O− patient gets O− units or, if none, a denial that lists the
compatible donors worth calling plus an automatic broadcast to matching
available donors in the hospital's city. If you have time, mention that
urgency is not a sort key but a *strategy switch* — emergency ranking puts
ready-today donors above nearby-but-recent donors.

---

## Slide 7 — The laboratory gate: TTI screening (1:00)

**On slide:**
- Every bag is born **UNTESTED** — invisible to the stock pool
- Lab enters 4 markers: HIV · hepatitis B · hepatitis C · syphilis
- All non-reactive → AVAILABLE → reservable
- Any reactive → DISCARDED, reason recorded, donor guided to counselling
- The gate is *structural*: nothing to forget, no view to bypass

**Notes:** Your best new material — this is where you show you studied BSIS
and then *built* its core safety idea. Explain the structural claim plainly:
reserve and issue queries only ever see AVAILABLE bags, so an unscreened or
reactive unit is unissuable everywhere at once. Mention the hard edges in one
sentence: partial entries are refused, completed screenings are immutable, and
a unit that clears after expiry is expired, never released.

---

## Slide 8 — Correctness, concurrency, audit (1:00)

**On slide:**
- Computed, never stored: stock and eligibility derived from rows
- `select_for_update` + status re-checks: **a bag cannot be issued twice**
- Reservations pinned to their request — two requests never share a bag
- Every mandated action writes an audit row that survives deletion

**Notes:** The engineering-credibility slide. Tell the race story in words:
two staff accept two requests at the same moment; each reservation is locked,
re-checked, and pinned to its own request, so the same bag can never satisfy
both. Then the audit line: the log references entities loosely, so deleting
the bag does not delete the evidence. If a panelist probes any claim here, you
have the tests — say so and land slide 9.

---

## Slide 9 — Evidence it works (1:00)

**On slide:**
- **228 tests**, incl. a full end-to-end walkthrough over real HTTP
- Covers: race safety, reservation isolation, TTI gate, privacy partitions,
  session timeout, every page for every role
- Privacy: gated ID streaming · role-scoped querysets · 15-min idle sessions
- Graceful degradation: retrying SMTP, swappable SMS (SasuSync / Africa's
  Talking)

**Notes:** Do not read the numbers — point at them. One sentence per line:
the e2e test is the demo story automated; privacy is enforced in views and
querysets, not promises; the notification stack fails soft because Ghanaian
networks fail often. Offer the live demo here with the 90-second script from
PANEL_PREP.md if the chairman allows one.

---

## Slide 10 — Honest limits, roadmap, close (0:30)

**On slide:**
- Next: adverse-reaction reporting · donor-deferral registry · inter-hospital
  transfer · PostgreSQL deployment
- Known scope cuts: component processing, multi-country (deliberate)
- **"CBODS connects the people who give with the people who need —
  safely, accountably, and verifiably."**

**Notes:** Name the limits before the panel does — it converts attacks into
agreements. One line each for the four next steps. Deliver the closing
sentence from memory, pause two seconds, then: "Thank you — questions."

---

## Delivery tips

- Rehearse slides 7 and 8 hardest; they carry the technical credibility.
- Keep the exact test names in your back pocket (double-issue race safety,
  per-request reservation isolation) — specificity defuses follow-ups.
- If time collapses, cut slide 2 entirely and fold its first line into slide
  3's opening.
