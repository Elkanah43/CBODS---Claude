"""Build a speaker-notes and defence guide (PDF) for the updated CBODS presentation.

Reads nothing at run time except the deck's own slide count; the guide text is authored
here so it can be regenerated whenever the deck changes.  HTML is written to a temporary
file and printed to PDF with headless Chrome (no extra packages needed).

Output: CBODS_IT_Project_Presentation 2_SPEAKER_NOTES.pdf  beside the deck.
"""

from __future__ import annotations

import html
import os
import subprocess
import tempfile
from pathlib import Path

DECK = Path(r"C:\Users\Elkanah\Desktop\Sch\!!P\CBODS_IT_Project_Presentation 2_UPDATED.pptx")
OUT = Path(r"C:\Users\Elkanah\Desktop\Sch\!!P\CBODS_IT_Project_Presentation 2_SPEAKER_NOTES.pdf")

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# --------------------------------------------------------------------------- #
# Slide-by-slide guidance.  Times assume a 15-minute slot; see the timing table.
# --------------------------------------------------------------------------- #
SLIDES = [
    dict(
        n=1, title="GHANA COMMUNICATION TECHNOLOGY UNIVERSITY",
        time="0:20", total="0:20",
        purpose="Open calmly, get your names on the record, and name the project once.",
        say=(
            "Good morning. We are Kofi Appianing Oware, Louis Frimpong and Nana Kwame Ansu "
            "Amankwah, and our project is the Design and Implementation of a Centralised "
            "Blood and Organ Donor System \u2014 CBODS. It is a web-based platform for donor "
            "management and blood matching, supervised by Mr. Isaac Baffour Senkyire."
        ),
        cues=[
            "Give each name slowly and clearly, with the index number only if the panel asks.",
            "Say the acronym CBODS once, correctly \u2014 you will use it for the rest of the talk.",
            "Do not read the whole title card aloud; the title is already on the screen.",
        ],
    ),
    dict(
        n=2, title="BACKGROUND TO THE STUDY",
        time="0:55", total="1:15",
        purpose="Establish why blood and organ donation is a real problem, globally and in Ghana.",
        say=(
            "Blood transfusion is essential for emergency care, surgery, childbirth and the "
            "management of chronic disease, and blood cannot be manufactured \u2014 every unit "
            "comes from a human donor. The World Health Organization reports that in 2023 "
            "high-income countries collected 28.9 units per thousand people, against 4.5 in "
            "low-income countries. Ghana collected 187,280 units in 2024 against a "
            "recommended requirement of about 308,000, and voluntary donations fell from 40 "
            "per cent to 29 per cent, which pushes hospitals onto replacement donors. When a "
            "hospital cannot reach a suitable donor quickly it falls back on phone calls, "
            "personal networks and social media. Organ donation carries the same dependency, "
            "with even more sensitive personal data, and no single platform in Ghana combines "
            "all of these needs."
        ),
        cues=[
            "Land the pair of numbers \u2014 187,280 against 308,000. That is the sentence the panel will remember.",
            "The last bullet is the hook for the whole project; pause after it before moving on.",
        ],
    ),
    dict(
        n=3, title="PROBLEM STATEMENT",
        time="1:00", total="2:15",
        purpose="Turn the background into five concrete problems and one consequence.",
        say=(
            "The current approach is fragmented, and that shows up in five ways. There is no "
            "centralised registry, so a donor registered at one facility is invisible to "
            "another. Compatibility is checked by eye, which is slow and error-prone. "
            "Inventory tracking is poor, so bags with a short shelf life expire unnoticed and "
            "are wasted. Organ donation has no structured workflow, so consent and approval "
            "are informal with no audit trail. And privacy and audit are weak, because paper "
            "or duplicated records increase the risk of unauthorised access to sensitive "
            "data. The consequence is that patients wait longer, stock is wasted, and "
            "hospitals fall back on phone calls and personal networks in an emergency."
        ),
        cues=[
            "Name each problem in four or five words, do not read the bullet in full \u2014 the room can read.",
            "Finish on the consequence line; it is your bridge to the aim.",
        ],
    ),
    dict(
        n=4, title="AIM & OBJECTIVES",
        time="0:45", total="3:00",
        purpose="State the aim and the three objectives the panel will mark you against.",
        say=(
            "Our aim was to design and develop a centralised blood and organ donor system "
            "that provides a single, secure platform for donor registration, automated blood "
            "matching and hospital-level management of inventory and donation requests. We "
            "set three objectives. First, to build a centralised donor registry with identity "
            "verification and an approval workflow. Second, to implement automated ABO and Rh "
            "compatibility matching for blood requests. Third, to give hospital staff "
            "inventory tools with expiry tracking and first-expiry-first-out reservation. "
            "Later I will show you how each of those three objectives was tested."
        ),
        cues=[
            "Say \u201cthree objectives\u201d explicitly \u2014 that is the number you are assessed on.",
            "The promise at the end (\u201cI will show you how each was tested\u201d) is deliberate; you keep it on slide 16.",
        ],
    ),
    dict(
        n=5, title="SIGNIFICANCE OF THE STUDY",
        time="0:35", total="3:35",
        purpose="Show the design is grounded in accepted blood-service principles, not invented.",
        say=(
            "CBODS is built on principles that are already established. Voluntary, "
            "non-remunerated donation is the safest source of supply. Every unit must be "
            "traceable to its donor. Screening for transfusion-transmissible infections is "
            "mandatory before any transfusion \u2014 that principle is the reason the system has a "
            "laboratory gate, which I will come back to. Inventory discipline matters because "
            "blood has a shelf life of only thirty-five to forty-two days. Organ donation "
            "requires explicit consent and ethical oversight. And national transfusion "
            "services show that centralised management works. CBODS encodes those principles "
            "through traceability, automated matching, expiry tracking and an immutable audit "
            "trail."
        ),
        cues=[
            "Flag the screening bullet \u2014 you will point back to it when you reach the laboratory gate.",
            "Keep this slide brisk; it is context, not a result.",
        ],
    ),
    dict(
        n=6, title="LITERATURE REVIEW",
        time="0:55", total="4:30",
        purpose="Show what exists already, that the algorithms are settled in the literature, "
                "and where the gap is.",
        say=(
            "The literature points in one direction. The WHO recommends national blood "
            "supply networks for coordinated collection, testing and distribution. ABO and Rh "
            "compatibility rules are fixed and well documented, which makes them suitable for "
            "encoding \u2014 and More and colleagues show the check can be built as a decision "
            "tree over the ABO and Rh types, with requests prioritised by urgency. Donor "
            "eligibility is settled the same way: a two-stage rule that checks basic criteria "
            "first and complex health metrics second, which Zulfikar and colleagues classified "
            "with decision trees and Naive Bayes. CBODS applies those rules as transparent "
            "logic rather than a classifier, so every decision can be explained. "
            "Abdul-Gafaru and colleagues connected donors to recipients, but without "
            "inventory or organ workflows, and Obeagu and Alsadi could not identify an "
            "African system with all the required features. The gap is clear: no existing "
            "system combines a centralised registry, compatibility matching, inventory "
            "management and an organ workflow."
        ),
        cues=[
            "Do not read every citation; name the source and give one clause for each.",
            "The gap sentence at the end is the point of the slide \u2014 deliver it slowly.",
            "If you are behind, drop the Zulfikar clause; the More citation is the one that "
            "carries the design decisions.",
            "If asked why you did not use machine learning, answer from this slide: the "
            "prototype must explain every decision, and the thresholds are institution-configurable.",
        ],
    ),
    dict(
        n=7, title="LITERATURE REVIEW (CONT.)",
        time="0:40", total="5:10",
        purpose="Say precisely how CBODS differs from each system reviewed.",
        say=(
            "So how does CBODS differ? Against the manual National Blood Service process, it "
            "centralises donor information digitally across hospitals. Against BSIS, which "
            "computerised the national value chain but stays at blood-centre level \u2014 it has "
            "no hospital-level screening, stock management or request workflow \u2014 CBODS adds "
            "all three. Against Abdul-Gafaru's system, it adds inventory management, expiry "
            "tracking and the organ donation workflow. None of the reviewed systems combines "
            "all of these capabilities in one platform, and that is the space this project "
            "occupies."
        ),
        cues=[
            "Three comparisons, three sentences \u2014 resist adding more detail here.",
            "If you are short of time, this slide can be compressed to the final sentence.",
            "The BSIS half of this slide moved here from slide 6, so do not go back to it there.",
        ],
    ),
    dict(
        n=8, title="METHODOLOGY",
        time="1:10", total="6:20",
        purpose="Justify Agile and walk the six phases, introducing the laboratory gate.",
        say=(
            "We used an Agile, iterative approach. The system spans several distinct areas \u2014 "
            "donor management, inventory, requests and organs \u2014 that can each be built and "
            "tested as a separate increment. Waterfall was considered and rejected, because "
            "it requires all requirements to be frozen before design and testing only at the "
            "end, which contradicts phased delivery. Work proceeded through six phases. "
            "Phase one was the foundation: accounts, roles, donor registration and the "
            "administrator's approval workflow. Phase two added screening and donation "
            "recording, together with the donation sites directory where a donor books a "
            "visit. A recorded donation creates the bag in an untested state, and the unit "
            "is held out of the usable pool until the laboratory screening \u2014 HIV, "
            "hepatitis B, hepatitis C and syphilis \u2014 clears it or discards it. Phase three "
            "added inventory and expiry tracking across untested, available and reserved "
            "units, with low-stock alerts and stock levels computed rather than stored. "
            "Phase four added requests, compatibility matching and first-expiry-first-out "
            "reservation, and the emergency broadcast when stock is short. Phase five organs, "
            "notifications and the audit log, and phase six the administrative dashboards, "
            "CSV export and the end-to-end verification test. Each phase was tested before "
            "the next began."
        ),
        cues=[
            "The laboratory gate first appears here. Say the four markers once, clearly.",
            "If you are running long, drop the Waterfall sentence \u2014 keep the six phases.",
        ],
    ),
    dict(
        n=9, title="SYSTEMS ANALYSIS",
        time="0:45", total="7:05",
        purpose="Present the data design: thirteen tables, eight modules, and the core tables.",
        say=(
            "The database has thirteen tables across eight application modules. The User "
            "table holds every account with its role. Three tables hang off it directly: the "
            "Hospital table records each registered facility, StaffProfile links a staff "
            "account to one hospital so their access is scoped to that hospital alone, and "
            "the Donor table holds the full donor profile, blood group and registration "
            "status. ScreeningRecord captures the outcome of each two-stage screening, "
            "Donation records each completed donation, and \u2014 the newest addition \u2014 "
            "TTITestRecord holds the laboratory screening for a donation, linked one-to-one, "
            "which is what decides whether the bag is released or discarded."
        ),
        cues=[
            "Say \u201cthirteen tables\u201d confidently; expect a follow-up asking you to name them.",
            "TTITestRecord is the one table the panel has not seen before \u2014 give it the extra sentence.",
        ],
    ),
    dict(
        n=10, title="SYSTEMS ANALYSIS (CONT.)",
        time="0:40", total="7:45",
        purpose="Finish the table list and state the two design decisions that matter most.",
        say=(
            "The operational tables are BloodBag, which holds a single unit with its expiry "
            "date and status; BloodRequest, which holds a patient request with its urgency; "
            "Appointment, which holds a donor's visit booking and the hospital's decision; "
            "OrganDonationRequest, which holds the organ workflow; Notification; and "
            "AuditLog, which holds immutable action records. Two design decisions run through "
            "all of it. Stock levels are computed from the records on every read rather than "
            "stored as a cached counter, so the figure on screen can never drift from the "
            "underlying stock. And every operation that changes the state of a bag or a "
            "request runs as an atomic transaction with row-level locking."
        ),
        cues=[
            "\u201cComputed, not cached\u201d is a favourite examiner question \u2014 be ready to explain why it removes drift.",
            "Do not read the table names one by one if you are behind; name three and summarise.",
        ],
    ),
    dict(
        n=11, title="SYSTEMS ANALYSIS (CONT.)",
        time="0:35", total="8:20",
        purpose="Show the data model as a picture, then stop.",
        say=(
            "This is the data model. It shows the relationships you have just heard: one "
            "hospital to many staff profiles, bags, donations and requests; one donor to many "
            "screenings, donations and organ requests; one donation to exactly one "
            "laboratory record and to the bag it produced; and a request to the bags reserved "
            "for it."
        ),
        cues=[
            "Name the figure aloud (for example, \u201cFigure 3.3, the entity-relationship model\u201d) so the panel can refer to it later.",
            "Point at one relationship, say it, and move on \u2014 do not walk the whole diagram.",
            "The image on this slide carries no caption; add one before the defence if you can.",
        ],
    ),
    dict(
        n=12, title="SYSTEM DESIGN",
        time="1:00", total="9:20",
        purpose="Explain the three-tier architecture and the five decisions behind it.",
        say=(
            "CBODS uses a three-tier design. The presentation tier is HTML, CSS and "
            "JavaScript with Bootstrap, vendored locally, with responsive sidebar navigation "
            "and a light and dark theme. The application tier is Django \u2014 views, a service "
            "layer that holds the business rules, and models that define the data. The data "
            "tier is a relational database, SQLite in development, holding thirteen tables "
            "across eight modules. Five decisions are worth drawing out. The service layer "
            "separates business rules from view logic, so a rule is written once and can be "
            "tested on its own. Stock levels are computed, never cached. Reservation and "
            "issue are atomic transactions with row-level locking. The audit log uses loose "
            "references so entries survive even if the record they describe is deleted. And "
            "every change to a bag's status passes through one audited service function, "
            "which means the laboratory gate cannot be bypassed by any other route through "
            "the code."
        ),
        cues=[
            "The last bullet is the architectural heart of the project \u2014 slow down for it.",
            "\u201cLoose references\u201d is worth one sentence of plain English: the log outlives the record.",
        ],
    ),
    dict(
        n=13, title="SYSTEM DESIGN (CONT.)",
        time="0:50", total="10:10",
        purpose="Show that privacy and safety were designed in, not added afterwards.",
        say=(
            "Security is layered. Role-based access control gives the four roles \u2014 "
            "administrator, hospital staff, donor and patient \u2014 only the permissions they "
            "need. Identity documents can be viewed only by administrators, through one "
            "restricted view. Queries are privacy-aware: a donor sees only their own records "
            "and hospital staff see only their own hospital's data, which is enforced at the "
            "query level rather than hidden in the interface. The laboratory screening gate "
            "holds every donated unit out of the usable stock until all four markers are "
            "clear. Sessions expire after fifteen minutes of inactivity, passwords are "
            "hashed, and password reset links expire after twelve hours. CSRF protection "
            "guards every state-changing request, every significant action is written to an "
            "immutable audit log, input is validated at the boundaries, and the production "
            "deployment settings disable debug and enforce HTTPS and secure cookies."
        ),
        cues=[
            "\u201cEnforced at the query level, not hidden in the interface\u201d is the answer to the obvious privacy challenge.",
            "This slide has nine dense bullets \u2014 group them as access control, safety, session, audit, deployment.",
        ],
    ),
    dict(
        n=14, title="SYSTEM DESIGN (CONT.)",
        time="0:35", total="10:45",
        purpose="Show the design as a picture and connect it back to the tiers.",
        say=(
            "This diagram shows the design in one view. Reading it left to right, the user "
            "interacts with the presentation layer, which talks to the Django application "
            "layer, where the service layer holds the rules and the models define the data, "
            "and that in turn reads and writes the relational database."
        ),
        cues=[
            "Name the figure aloud, point at the tier you are naming, and stop.",
            "The image on this slide carries no caption; add one before the defence if you can.",
        ],
    ),
    dict(
        n=15, title="SYSTEM IMPLEMENTATION",
        time="0:45", total="11:30",
        purpose="State the stack, and pre-empt the dependency and hosting questions.",
        say=(
            "The stack is entirely free and open source. On the backend, Python 3 with "
            "Django 5.2, the Django ORM so there is no hand-written SQL, SQLite as the "
            "development database, and a service layer that separates business logic from "
            "the views. On the frontend, HTML5 for structure, CSS3 for styling, vanilla "
            "JavaScript for interactivity, Bootstrap for the responsive grid and components, "
            "and the Inter typeface. Bootstrap and Inter are vendored locally rather than "
            "loaded from a CDN, so the system does not depend on an internet connection to "
            "look correct."
        ),
        cues=[
            "\u201cNo CDN, vendored locally\u201d answers the reliability question before it is asked.",
            "If asked about SQLite, say the ORM makes a move to PostgreSQL a configuration change \u2014 it is listed as future work.",
        ],
    ),
    dict(
        n=16, title="TESTING AND EVALUATION",
        time="1:05", total="12:35",
        purpose="Show the evidence: how many tests were written, and which ones prove each "
                "of the three objectives.",
        say=(
            "Implementation is only half the story; this slide is the evidence. The system "
            "was evaluated through two hundred and sixty-four automated tests across "
            "forty-seven test classes, and every one of them passes. The module split is on "
            "the slide. What matters more is that each of our three objectives is tied to "
            "the tests that prove it. The registry and identity verification are proven by "
            "the privacy partition tests, the identity-document privacy tests, the hospital "
            "approval tests and the duplicate-registration tests. Matching is proven by the "
            "compatibility tree tests, which walk the full matrix of sixty-four ABO and Rh "
            "combinations, together with the denial-with-alternatives and request lifecycle "
            "tests. Inventory is proven by the donation-blocking tests, the laboratory gate "
            "tests covering untested units and reactive discard, the FEFO reservation "
            "tests, and the end-to-end test. The suite falls into seven categories: "
            "boundary conditions, workflow lifecycles, the laboratory safety gate, access "
            "control and per-hospital isolation, input validation, message delivery, and "
            "page rendering."
        ),
        cues=[
            "Two hundred and sixty-four is the number the panel will remember \u2014 say it slowly.",
            "Do not read the test names off the slide; say the count, then name the objective each set proves.",
            "If a panelist names a class, say what it asserts \u2014 do not guess.",
            "Never trim this slide when you are running late. Trim slides 6, 7 or 11 instead.",
        ],
    ),
    dict(
        n=17, title="CONCLUSIONS AND RECOMMENDATIONS",
        time="1:15", total="13:50",
        purpose="Close the loop: three objectives, the evidence, and what comes next.",
        say=(
            "In conclusion, all three objectives were achieved. A centralised donor registry "
            "with identity verification; automated ABO and Rh compatibility matching, "
            "verified against all sixty-four group combinations; and hospital-level "
            "inventory with a laboratory screening gate, first-expiry-first-out reservation "
            "and expiry tracking \u2014 alongside a structured organ donation workflow. All of "
            "this was built and validated by two hundred and sixty-four passing automated "
            "tests, and donor privacy is protected by role-based access control, restricted "
            "access to identity documents and an immutable audit log. For future work we "
            "recommend three things: deploying CBODS on PostgreSQL with cloud hosting and "
            "HTTPS, and a mobile app with push notifications; extending it with crossmatching "
            "and integration with laboratory information systems, then connecting it to NBS "
            "Ghana and BSIS for real donor data exchange; and institutional partnerships \u2014 "
            "piloting it with real hospitals for live data and user acceptance testing, and "
            "promoting adoption by the Ministry of Health and academic institutions as a "
            "teaching platform."
        ),
        cues=[
            "You showed the evidence on slide 16; here you are closing the loop. Say the three objectives and the count, then stop.",
            "Repeat \u201cthree objectives\u201d here \u2014 slide 4 promised this and the panel will be checking.",
            "Do not add new content on this slide; it is a summary and the last thing they hear.",
        ],
    ),
    dict(
        n=18, title="REFERENCES",
        time="0:10", total="14:00",
        purpose="Acknowledge sources and hand over.",
        say=(
            "These are the sources behind the work. Thank you for listening \u2014 we are happy to "
            "take your questions."
        ),
        cues=[
            "Do not read the list. Name two or three key sources only if the panel asks.",
            "Stop speaking on the thank-you; let the panel speak next.",
        ],
    ),
]

TIMING = [
    ("1", "Title and introduction", "0:20", "0:20"),
    ("2", "Background to the study", "0:55", "1:15"),
    ("3", "Problem statement", "1:00", "2:15"),
    ("4", "Aim and objectives", "0:45", "3:00"),
    ("5", "Significance of the study", "0:35", "3:35"),
    ("6", "Literature review", "0:55", "4:30"),
    ("7", "Literature review (continued)", "0:40", "5:10"),
    ("8", "Methodology and six phases", "1:10", "6:20"),
    ("9", "Data design: core tables", "0:45", "7:05"),
    ("10", "Data design: operational tables", "0:40", "7:45"),
    ("11", "Data model diagram", "0:35", "8:20"),
    ("12", "System architecture", "1:00", "9:20"),
    ("13", "Security design", "0:50", "10:10"),
    ("14", "Design diagram", "0:35", "10:45"),
    ("15", "Technology stack", "0:45", "11:30"),
    ("16", "Testing and evaluation", "1:05", "12:35"),
    ("17", "Conclusions and recommendations", "1:15", "13:50"),
    ("18", "References and hand-over", "0:10", "14:00"),
]

TRIM = [
    ("Never trim slide 16 (testing and evaluation) \u2014 it is the evidence for the marks.", "nothing"),
    ("Drop the Waterfall sentence on slide 8.", "saves about 15 seconds"),
    ("Compress slide 7 to its final sentence.", "saves about 15 seconds"),
    ("On slide 6, name three studies instead of five.", "saves about 15 seconds"),
    ("On slides 9 and 10, name three tables each instead of all of them.", "saves about 25 seconds"),
    ("On slide 11 and slide 14, name the figure and skip the walkthrough.", "saves about 25 seconds"),
    ("On slide 13, group the nine bullets into four headings.", "saves about 20 seconds"),
]

NUMBERS = [
    ("264", "passing automated tests", "the headline number \u2014 say it on slide 16"),
    ("47", "test classes", "across the eight modules"),
    ("13", "database tables", "across eight application modules"),
    ("8", "application modules", "accounts, hospitals, donors, inventory, requests, organs, notifications, audit"),
    ("4", "user roles", "administrator, hospital staff, donor, patient"),
    ("6", "development phases", "each tested before the next began"),
    ("3", "objectives", "registry, matching, inventory tools"),
    ("64", "ABO/Rh group combinations", "the full compatibility matrix, verified"),
    ("4", "infection markers", "HIV, hepatitis B, hepatitis C, syphilis"),
    ("6", "bag states", "untested, available, reserved, issued, expired, discarded"),
    ("35", "days shelf life", "expiry computed as collection date plus thirty-five days"),
    ("7", "days expiry warning", "bags inside seven days of expiry are highlighted"),
    ("3", "units low-stock threshold", "staff are notified below it"),
    ("15", "minutes session timeout", "idle sessions end automatically"),
    ("12", "hours password-reset expiry", "the reset link lifetime"),
    ("187,280 vs 308,000", "units collected vs needed in Ghana, 2024", "the most memorable contrast in the deck"),
    ("28.9 vs 4.5", "units per 1,000 people, high vs low income, 2023", "WHO figures on slide 2"),
]

QA = [
    (
        "You say three objectives were achieved. How do you know?",
        "Each objective was treated as an evaluation criterion and mapped to the tests that "
        "prove it. Registry and identity verification are covered by the privacy-partition "
        "and identity-document privacy tests together with the hospital approval tests; "
        "matching is covered by the compatibility-tree tests, which exercise the full "
        "matrix, and the request lifecycle tests for FEFO reservation; and inventory is "
        "covered by the donation-blocking tests, the laboratory gate tests, the request "
        "lifecycle tests and the end-to-end test that also runs the expiry command. Every "
        "one of them passes.",
    ),
    (
        "How many tests did you write, and what do they cover?",
        "Two hundred and sixty-four tests in forty-seven test classes. They fall into seven "
        "categories: boundary conditions, complete workflow lifecycles, the laboratory "
        "safety gate, access control and per-hospital data isolation, input validation, "
        "message delivery, and page rendering, plus an end-to-end walkthrough of the full "
        "demo story. By module, accounts has 109 tests in 16 classes, hospitals 62 in 11, "
        "donors 49 in 9, requests 11 in 4, inventory 11, notifications 6 in 2, audit 6 in 2, "
        "and the end-to-end and render suites 10 in 2.",
    ),
    (
        "Which tests prove the laboratory screening gate?",
        "TTIGateTests, eleven tests in the inventory module. They confirm that recording a "
        "donation creates the bag in the untested state together with its laboratory "
        "record; that an untested bag is excluded from the stock figures and cannot be "
        "reserved, although staff can still see it in the inventory; that a partial "
        "screening neither releases nor discards the unit; that all four markers "
        "non-reactive moves the bag into the available pool, and that a completed screening "
        "cannot be entered a second time; that a reactive marker discards the bag with the "
        "markers recorded as the reason and notifies the donor to seek counselling and "
        "confirmatory testing; that a screening which omits a marker, or names a marker "
        "that does not exist, is rejected; and that a unit which reaches its expiry date "
        "while still awaiting the laboratory is marked expired rather than released.",
    ),
    (
        "What happens if a donor's blood tests positive for an infection?",
        "The unit is discarded immediately \u2014 it never enters the available pool. The "
        "reactive markers are recorded as the reason on the laboratory record, the status "
        "change is written to the audit log through the same single service function that "
        "handles every status change, and the donor is notified and advised to seek "
        "counselling and confirmatory testing. A partial screening does neither: an "
        "incomplete result neither releases nor discards the unit.",
    ),
    (
        "How do you guarantee an untested unit can never be transfused?",
        "In three independent ways. The bag is created in the untested state, so it cannot "
        "be reserved. Untested units are excluded from the computed stock figures, so no "
        "request can draw on them. And the matching component is given only the bags that "
        "have passed the gate. Underneath all three, every status change goes through one "
        "audited service function, so there is no second code path that could release a "
        "unit early.",
    ),
    (
        "What stops two staff members reserving the same bag at the same time?",
        "Reservation and issue each run as a single database transaction with row-level "
        "locking. The second transaction blocks until the first commits, then re-reads the "
        "bag and finds that its status is no longer available. A dedicated concurrency test "
        "exercises exactly this situation.",
    ),
    (
        "How do you protect donor privacy?",
        "Four layers. Role-based access control scopes every action to a role; hospital "
        "staff can see only their own hospital's data and donors only their own records, "
        "enforced in the queries themselves rather than in the templates; identity documents "
        "are reachable only by administrators through one restricted view; and every "
        "significant action is recorded in an audit log with the actor, the timestamp and "
        "the details, using loose references so the entry survives even if the record is "
        "deleted.",
    ),
    (
        "Why does the system use SQLite? Is that a weakness?",
        "It is a deliberate choice for a prototype \u2014 SQLite needs no server, which makes the "
        "system easy to demonstrate and mark. Because all database access goes through the "
        "Django ORM and no raw SQL is used, moving to PostgreSQL is a configuration change "
        "rather than a rewrite. Production deployment on PostgreSQL is the first "
        "recommendation in our future work.",
    ),
    (
        "How does the emergency path work when stock is short?",
        "When a hospital cannot meet a request from its own compatible stock, the system "
        "searches for approved, available donors whose blood group is compatible with the "
        "request and who are registered in the same city as the hospital, and sends them an "
        "urgent broadcast through the notification service. This replaces the phone calls "
        "and personal networks that the literature describes.",
    ),
    (
        "Why first-expiry-first-out?",
        "Because blood has a fixed shelf life, so the oldest suitable unit must be used "
        "first or it is wasted. FEFO is applied when bags are selected for reservation, and "
        "combined with automatic expiry marking and low-stock alerts it directly attacks the "
        "wastage problem described in the problem statement.",
    ),
    (
        "Why Agile rather than Waterfall?",
        "The system spans eight modules with quite different rules, and requirements in "
        "later modules clarified the design of earlier ones. Agile let us deliver a working "
        "version in each of the six phases, with testing at the end of every phase, instead "
        "of freezing all requirements up front and testing only at the end.",
    ),
    (
        "What did you not do?",
        "The system does not connect to laboratory equipment, hospital information systems "
        "or the national blood service infrastructure, and it is evaluated with demo data "
        "rather than real records, so usability in a clinical setting has not been assessed. "
        "It performs compatibility matching but not crossmatching, and the organ workflow "
        "covers request, review and approval rather than matching organs to recipients. "
        "Those are all in our future work.",
    ),
    (
        "What is new here, compared with existing systems?",
        "The core novelty is that the laboratory screening is a gate inside the system "
        "rather than a note beside it. A unit cannot reach the usable pool, cannot be "
        "counted in stock and cannot be matched to a request until all four infection "
        "markers have been cleared, and every status change passes through one audited "
        "function. Combined with per-hospital inventory, FEFO reservation, the emergency "
        "broadcast and the organ workflow in one platform, that is what the reviewed systems "
        "do not offer.",
    ),
]

CHECKLIST = [
    "Confirm the presentation slot length and delete the timing table if the guide is printed double-sided.",
    "Add captions to the two image slides (11 and 14) so the panel can name the figures.",
    "Confirm you are presenting the eighteen-slide deck \u2014 Testing and Evaluation must follow System Implementation.",
    "Check slide 18 (references) still fits \u2014 the corrected references are slightly longer; reduce the font if the last entry spills.",
    "Open the deck on the defence laptop and check the theme fonts render, especially the Inter typeface.",
    "Rehearse aloud twice with a timer; the plan runs to about 14 minutes, so there is about a minute of slack.",
    "Rehearse the demo separately: sign in as donor, book an appointment, sign in as staff, confirm it, then record a donation and clear the laboratory screening.",
    "Prepare a fallback: keep screenshots of the main pages in the deck in case the demo machine fails.",
    "Decide who answers which questions \u2014 architecture and data model, testing and evaluation, demo and interface \u2014 and say so at the hand-over.",
    "Learn the quick-reference numbers on the next page by heart.",
]

EXTRA = [
    ("Testing and evaluation \u2014 now in the deck as slide 16",
     "The 264 tests, the 47 classes and the objective-to-evidence mapping sit on slide 16, "
     "between System Implementation and the Conclusions, which is where an evaluation "
     "section belongs in the report as well."),
    ("User interface screenshots (after slide 16)",
     "Four captioned screenshots: the login page, the donor dashboard, the laboratory "
     "screening queue and the inventory dashboard with untested units shown separately, "
     "and the donation sites directory with appointment booking. These also serve as demo "
     "backup."),
    ("Limitations (before the conclusions)",
     "One slide drawn from scope, challenges and future work: no external system "
     "integration, no real data, prototype hosting, no crossmatching, no organ matching."),
    ("Backup slides (after the references)",
     "The entity-relationship diagram, the use-case diagram, the compatibility matrix and "
     "one code excerpt, so you can jump to evidence during questioning without disturbing "
     "the main flow. The full forty-seven-class test catalogue is in the appendix document."),
]


def esc(t: str) -> str:
    return html.escape(t, quote=False)


def build_html() -> str:
    css = """
    @page { size: A4; margin: 16mm 14mm 14mm 14mm; }
    * { box-sizing: border-box; }
    body { font-family: "Segoe UI", Calibri, Arial, sans-serif; font-size: 10.2pt;
           color: #1c1c1c; line-height: 1.42; margin: 0; }
    h1 { font-size: 19pt; margin: 0 0 2mm 0; color: #7a1020; }
    h2 { font-size: 13pt; margin: 7mm 0 2mm 0; color: #7a1020;
         border-bottom: 1.1pt solid #7a1020; padding-bottom: 1mm; }
    h3 { font-size: 11.4pt; margin: 4mm 0 1.5mm 0; color: #1c1c1c; }
    .lead { font-size: 10.6pt; color: #444; margin: 0 0 3mm 0; }
    .meta { font-size: 9pt; color: #666; margin-bottom: 4mm; }
    .meta b { color: #333; }
    table { width: 100%; border-collapse: collapse; margin: 2mm 0 3mm 0; }
    th, td { border: 0.5pt solid #c9c9c9; padding: 1.3mm 2mm; vertical-align: top;
             text-align: left; }
    th { background: #f2e6e8; font-size: 9.4pt; }
    td { font-size: 9.6pt; }
    td.c, th.c { text-align: center; white-space: nowrap; }
    .card { border: 0.8pt solid #bfbfbf; border-left: 3.2pt solid #7a1020;
            padding: 2.6mm 3mm 2mm 3mm; margin: 0 0 3.4mm 0;
            page-break-inside: avoid; break-inside: avoid; }
    .card h3 { margin: 0 0 1.2mm 0; font-size: 11.6pt; }
    .card .when { font-size: 9pt; color: #7a1020; font-weight: 600; margin-bottom: 1.6mm; }
    .lbl { font-weight: 700; font-size: 9.4pt; color: #333; display: block;
           margin: 1.6mm 0 0.8mm 0; text-transform: uppercase; letter-spacing: 0.3pt; }
    .say { background: #faf7f7; border: 0.5pt solid #e2d5d7; padding: 2mm 2.6mm;
           margin: 0 0 1mm 0; font-size: 10pt; }
    ul { margin: 0.6mm 0 0 4.6mm; padding: 0; }
    li { margin-bottom: 0.9mm; font-size: 9.7pt; }
    .pagebreak { page-break-before: always; break-before: page; }
    .num td:first-child { font-weight: 700; color: #7a1020; white-space: nowrap; }
    .qa { page-break-inside: avoid; break-inside: avoid; margin-bottom: 3mm; }
    .qa .q { font-weight: 700; font-size: 10.2pt; color: #7a1020; }
    .qa .a { margin-top: 0.6mm; }
    .note { font-size: 9pt; color: #666; font-style: italic; }
    """
    out = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        "<title>CBODS \u2014 Speaker Notes and Defence Guide</title>",
        f"<style>{css}</style></head><body>",
        "<h1>CBODS \u2014 Speaker Notes and Defence Guide</h1>",
        "<p class='lead'>Design and Implementation of a Centralised Blood and Organ Donor "
        "System \u2014 a web-based platform for donor management and blood matching.</p>",
        "<p class='meta'><b>Matches:</b> CBODS_IT_Project_Presentation 2_UPDATED.pptx "
        "(18 slides) &nbsp;|&nbsp; <b>Presenters:</b> Kofi Appianing Oware (4211231051), "
        "Louis Frimpong (4211230103), Nana Kwame Ansu Amankwah (4211231035) &nbsp;|&nbsp; "
        "<b>Supervisor:</b> Mr. Isaac Baffour Senkyire &nbsp;|&nbsp; "
        "<b>Planned duration:</b> about 14 minutes, which leaves about a minute of slack in "
        "a 15-minute slot.</p>",
        "<h2>How to use this guide</h2>",
        "<p>Each slide has four parts: how long it should take, what the slide is <i>for</i>, "
        "a script you can speak almost word for word, and cues that flag the traps. The "
        "script is written to be said aloud, not read from the screen \u2014 the screen carries "
        "the headings and the numbers, your voice carries the meaning. If you are asked to "
        "shorten the talk, use the trimming list on the next page rather than dropping "
        "slides, and note that the numbers on the quick-reference page are the ones most "
        "likely to be tested in the questions.</p>",
        "<h2>Timing plan</h2>",
        "<table><tr><th class='c'>Slide</th><th>Topic</th><th class='c'>Time</th>"
        "<th class='c'>Running</th></tr>",
    ]
    for n, topic, t, tot in TIMING:
        out.append(f"<tr><td class='c'>{n}</td><td>{esc(topic)}</td>"
                   f"<td class='c'>{t}</td><td class='c'>{tot}</td></tr>")
    out.append("<tr><td class='c'>\u2014</td><td><b>Total</b></td>"
               "<td class='c'><b>14:00</b></td><td class='c'><b>14:00</b></td></tr></table>")
    out.append("<h2>If you are running long</h2><table>"
               "<tr><th>Trim</th><th class='c'>Saves</th></tr>")
    for what, how in TRIM:
        out.append(f"<tr><td>{esc(what)}</td><td class='c'>{esc(how)}</td></tr>")
    out.append("</table>")

    out.append("<div class='pagebreak'></div><h2>Slide-by-slide notes</h2>")
    for s in SLIDES:
        out.append("<div class='card'>")
        out.append(f"<h3>Slide {s['n']} \u2014 {esc(s['title'])}</h3>")
        out.append(f"<div class='when'>Time {s['time']} &nbsp;\u00b7&nbsp; "
                   f"running total {s['total']}</div>")
        out.append(f"<span class='lbl'>What this slide is doing</span>"
                   f"<div>{esc(s['purpose'])}</div>")
        out.append(f"<span class='lbl'>Say this</span>"
                   f"<div class='say'>{esc(s['say'])}</div>")
        out.append("<span class='lbl'>Cues</span><ul>")
        for c in s["cues"]:
            out.append(f"<li>{esc(c)}</li>")
        out.append("</ul></div>")

    out.append("<h2>Numbers to know by heart</h2>")
    out.append("<p class='note'>If you hesitate on one of these, the panel will notice. "
               "They are all drawn from the system as it stands.</p>")
    out.append("<table><tr><th class='c'>Number</th><th>What it is</th>"
               "<th>Why it matters</th></tr>")
    for v, what, why in NUMBERS:
        out.append(f"<tr><td class='c'>{esc(v)}</td><td>{esc(what)}</td>"
                   f"<td>{esc(why)}</td></tr>")
    out.append("</table>")

    out.append("<div class='pagebreak'></div>"
               "<h2>Likely questions and how to answer them</h2>")
    out.append("<p class='note'>Agree in advance who takes which category: architecture "
               "and data model, testing and evaluation, and interface and demonstration.</p>")
    for i, (q, a) in enumerate(QA, 1):
        out.append(f"<div class='qa'><div class='q'>{i}. {esc(q)}</div>"
                   f"<div class='a'>{esc(a)}</div></div>")

    out.append("<div class='pagebreak'></div>"
               "<h2>If you add slides before the defence</h2>")
    out.append(    "<p class='note'>These are the additions that would strengthen the talk "
    "most, in order of value. The testing slide is now in the deck as slide 16; the "
    "rest are not yet in the deck.</p>")
    for head, body in EXTRA:
        out.append(f"<h3>{esc(head)}</h3><p>{esc(body)}</p>")

    out.append("<h2>Pre-defence checklist</h2><ul>")
    for c in CHECKLIST:
        out.append(f"<li>{esc(c)}</li>")
    out.append("</ul>")
    out.append("</body></html>")
    return "\n".join(out)


def find_browser() -> str:
    for p in (CHROME, EDGE):
        if os.path.exists(p):
            return p
    raise SystemExit("no Chrome or Edge found for PDF printing")


def main() -> None:
    assert DECK.exists(), f"deck not found: {DECK}"
    html_text = build_html()

    with tempfile.TemporaryDirectory() as td:
        html_path = Path(td) / "speaker_notes.html"
        html_path.write_text(html_text, encoding="utf-8")
        profile = Path(td) / "profile"
        cmd = [
            find_browser(),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile}",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={OUT}",
            html_path.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if not OUT.exists():
            print(proc.stdout[-3000:])
            print(proc.stderr[-3000:])
            raise SystemExit("PDF was not produced")

    size = OUT.stat().st_size
    print(f"written: {OUT.name} ({size:,} bytes)")

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(OUT))
        print(f"pages: {len(reader.pages)}")
        first = reader.pages[0].extract_text() or ""
        print("first page starts:", " ".join(first.split())[:90])
    except Exception as exc:  # pragma: no cover
        print("pypdf check skipped:", exc)


if __name__ == "__main__":
    main()
