"""Build the paste-ready corrections for CBODS_NEW V7.2.docx.

Emits two files from one source of truth:
  * CBODS_CORRECTIONS.docx  - Word document whose replacement paragraphs match the
    thesis body (Times New Roman 12pt, justified) and whose Table 4.2 is a real
    Word table, so both can be copied straight into the master document.
  * CBODS_corrections.md    - the same text as readable markdown.

Read-only with respect to the master document.
"""
from __future__ import annotations

import html
import zipfile
from pathlib import Path

OUT_DOCX = Path("CBODS_CORRECTIONS.docx")
OUT_MD = Path("CBODS_corrections.md")

# --------------------------------------------------------------------------- #
# Table 4.2 - Summary of test results by module (verified against the live suite)
# --------------------------------------------------------------------------- #
TABLE_42_HEADER = ["Module", "Test class", "Number of tests", "Focus", "Result"]
TABLE_42_ROWS = [
    # Accounts
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
    # Donors
    ("Donors", "Stage1BoundaryTests", "4", "Age, weight and donation-interval boundaries"),
    ("Donors", "Stage2BoundaryTests", "2", "Haemoglobin and blood-pressure boundaries"),
    ("Donors", "DonationBlockingTests", "5", "Donation blocked for ineligible or unapproved donors"),
    ("Donors", "IdDocumentPrivacyTests", "4", "Document readable only by administrator"),
    ("Donors", "IdDocumentValidationTests", "3", "File type and size validation at upload"),
    ("Donors", "ContactPhoneValidationTests", "6", "Donor contact phone validated and stored in international form"),
    ("Donors", "DonationSitesTests", "8", "Approved, visible hospitals only; per-group stock, low-stock flag and ranking"),
    ("Donors", "DonorSelfServiceTests", "2", "Resubmit rejected registration, edit profile"),
    ("Donors", "AppointmentTests", "15", "Booking, staff confirm or decline, cancellation, access gates"),
    # Inventory
    ("Inventory", "TTIGateTests", "11", "Untested bag isolation, four-marker clearance, reactive discard, expiry while awaiting the lab"),
    # Requests_app
    ("Requests_app", "CompatibilityTreeTests", "1", "Full ABO/Rh compatibility matrix (8 groups)"),
    ("Requests_app", "DenyWithAlternativesTests", "2", "Incompatible donor denial with alternatives"),
    ("Requests_app", "RequestLifecycleTests", "7", "Accept, reserve (FEFO), fulfil, reject, emergency ranking"),
    ("Requests_app", "AvailabilityFormTests", "1", "Form shows only in-stock groups"),
    # Hospitals
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
    # Notifications
    ("Notifications", "NotificationEmailRoutingTests", "4", "Email follows the account address; one message per recipient"),
    ("Notifications", "NotificationEmailFailureTests", "2", "Failed sends logged, never raise, never break the action"),
    # Audit
    ("Audit", "CsvExportTests", "4", "Five report types, non-admin refused"),
    ("Audit", "PaginationTests", "2", "Donor search pagination, filter preservation"),
    # End-to-end and render
    ("End-to-end", "FullDemoFlowTests", "2", "Full demo story, expiry command, low-stock alert"),
    ("Render", "PageRenderTests", "8", "Every page renders for every permitted role"),
]
TABLE_42_TOTAL = (
    "All modules",
    "47 test classes",
    "264",
    "Boundary, workflow, safety-gate, access-control, validation, delivery and render tests",
)

# --------------------------------------------------------------------------- #
# Table 4.3 - Evaluation criteria and supporting test evidence (corrected rows)
# --------------------------------------------------------------------------- #
TABLE_43_HEADER = ["Objective", "Criterion", "Supporting tests"]
TABLE_43_ROWS = [
    (
        "Centralised donor registry",
        "Donors register once; records are verified and managed from a single platform",
        "PrivacyPartitionTests (role-based scoping), IdDocumentPrivacyTests (restricted document access), "
        "DonorSelfServiceTests (resubmit and edit), HospitalApprovalTests (hospital registration and approval), "
        "DuplicateEmailRegistrationTests, GhanaPhoneNumberTests and HospitalUsernameGenerationTests "
        "(unique, validated accounts)",
    ),
    (
        "Automated blood-group compatibility matching",
        "Requests are checked against compatible stock and donors",
        "CompatibilityTreeTests (full matrix), DenyWithAlternativesTests (incompatible donor handling), "
        "RequestLifecycleTests (FEFO reservation, emergency ranking)",
    ),
    (
        "Hospital inventory and request management",
        "Staff record donations, manage stock, track expiry, reserve and issue blood",
        "DonationBlockingTests (eligibility enforcement), TTIGateTests (laboratory gate, untested bag isolation, "
        "reactive discard), RequestLifecycleTests (accept, fulfil, reject), AvailabilityFormTests (in-stock groups "
        "only), FullDemoFlowTests (expiry command, low-stock alert)",
    ),
    (
        "Structured organ donation workflow",
        "Donors submit requests, hospitals review, administrator approves or rejects",
        "FullDemoFlowTests (organ request lifecycle from submission to approval)",
    ),
    (
        "Privacy and auditability",
        "Role-based access control, restricted document access, audit log",
        "PrivacyPartitionTests, IdDocumentPrivacyTests, ForgotPasswordGateTests and PasswordResetFlowTests "
        "(reset security), SessionTimeoutTests, CsvExportTests (audit log export), FullDemoFlowTests "
        "(audit log entries verified)",
    ),
]

# --------------------------------------------------------------------------- #
# Replacement text
# --------------------------------------------------------------------------- #
SECTIONS = [
    {
        "title": "1.  The test count - five sentences to change",
        "lead": "The suite now runs 264 tests in 47 test classes. Every place that states a count is listed "
                "below; each replacement is a complete sentence, ready to take the place of the one quoted.",
        "items": [
            {
                "where": "Abstract (page iv), second sentence.",
                "find": "The system was evaluated through 110 automated tests covering unit, workflow, "
                        "access-control, privacy and end-to-end scenarios, all of which passed.",
                "replace": [
                    "The system was evaluated through 264 automated tests across 47 test classes, covering "
                    "boundary conditions, full workflow lifecycles, access control and per-hospital data "
                    "isolation, the privacy of identity documents, input validation, email and SMS delivery, "
                    "the laboratory screening gate on donated units, page rendering and an end-to-end "
                    "walkthrough of the complete demo story; all of them passed."
                ],
            },
            {
                "where": "Section 4.1.3, the sentence immediately after Table 4.2.",
                "find": "A total of 110 test methods were executed across 27 test classes, covering all eight "
                        "modules of the system. All tests passed, confirming that the implemented system "
                        "behaves as specified.",
                "replace": [
                    "A total of 264 test methods were executed across 47 test classes, covering all eight "
                    "modules of the system: accounts (109 tests in 16 classes), hospitals (62 tests in 11 "
                    "classes), donors (49 tests in 9 classes), requests (11 tests in 4 classes), inventory "
                    "(11 tests), notifications (6 tests in 2 classes), audit (6 tests in 2 classes), and the "
                    "end-to-end and render suites (10 tests in 2 classes). All tests passed, confirming that "
                    "the implemented system behaves as specified."
                ],
            },
            {
                "where": "Section 4.3, Summary - the sentence beginning \"Testing was carried out through\".",
                "find": "Testing was carried out through 110 automated test methods across 27 test classes, "
                        "covering boundary conditions, full workflow lifecycles, access control, privacy of "
                        "identity documents, password-reset security, session management, page rendering and "
                        "an end-to-end walkthrough of the complete demo story.",
                "replace": [
                    "Testing was carried out through 264 automated test methods across 47 test classes, "
                    "covering boundary conditions, full workflow lifecycles, access control and per-hospital "
                    "data isolation, the privacy of identity documents, input validation, the delivery of "
                    "system email and SMS, the laboratory screening gate, password-reset security, session "
                    "management, page rendering and an end-to-end walkthrough of the complete demo story."
                ],
            },
            {
                "where": "Chapter Five, the passage beginning \"Lastly, the automated test suite\".",
                "find": "Lastly, the automated test suite of 110 tests across 27 test classes serves as a "
                        "practical example of how to test a multi-module web application systematically, "
                        "covering boundary conditions, workflow lifecycles, access control and privacy, and "
                        "an end-to-end walkthrough of the major user journeys.",
                "replace": [
                    "Lastly, the automated test suite of 264 tests across 47 test classes serves as a "
                    "practical example of how to test a multi-module web application systematically, "
                    "covering boundary conditions, workflow lifecycles, access control and privacy, input "
                    "validation, delivery-failure handling, the laboratory screening gate and an end-to-end "
                    "walkthrough of the major user journeys."
                ],
            },
            {
                "where": "Chapter Five, the final conclusion - the sentence beginning \"Testing was carried "
                         "out through\".",
                "find": "Testing was carried out through 110 automated tests covering boundary conditions, "
                        "workflow lifecycles, access control, privacy of identity documents, password-reset "
                        "security, session management, page rendering and an end-to-end walkthrough of the "
                        "major user journeys.",
                "replace": [
                    "Testing was carried out through 264 automated tests covering boundary conditions, "
                    "workflow lifecycles, access control, privacy of identity documents, input validation, "
                    "email and SMS delivery, password-reset security, session management, the laboratory "
                    "screening gate, page rendering and an end-to-end walkthrough of the major user journeys."
                ],
            },
        ],
    },
    {
        "title": "2.  Section 4.1.3 - the test categories now number seven",
        "lead": "The suite has grown well beyond boundary, workflow, access-control and render tests. One "
                "sentence changes and three category paragraphs are new. Read in order, the paragraphs should "
                "run: boundary, workflow, safety gate, access control and privacy, validation, delivery, render.",
        "items": [
            {
                "where": "Section 4.1.3, third paragraph, last sentence.",
                "find": "The test suite falls into four categories.",
                "replace": ["The test suite falls into seven categories."],
            },
            {
                "where": "Section 4.1.3 - new category paragraph, inserted after the workflow-tests paragraph "
                         "(the one beginning \"Workflow tests exercise the full lifecycle\").",
                "find": None,
                "insert": True,
                "replace": [
                    "Safety-gate tests verify the laboratory gate that every donated unit must pass before it "
                    "can be used, as described in Phase 2 of Section 4.1.2. They confirm that recording a "
                    "donation creates the bag in the untested state together with its laboratory screening "
                    "record; that an untested bag is excluded from the stock figures and cannot be reserved, "
                    "although hospital staff can see it in the inventory; that a partially entered screening "
                    "neither releases nor discards the bag; that entering all four markers as non-reactive "
                    "moves the bag into the available pool; that a completed screening cannot be entered a "
                    "second time; that a reactive marker discards the bag with the reactive markers recorded "
                    "as the reason and notifies the donor to seek counselling and confirmatory testing; that "
                    "a screening which omits a marker, or which names a marker that does not exist, is "
                    "rejected; and that a unit which reaches its expiry date while still awaiting the "
                    "laboratory is marked expired rather than released into the pool. The daily expiry "
                    "command is tested against untested bags as well as available and reserved ones."
                ],
            },
            {
                "where": "Section 4.1.3 - two new category paragraphs, inserted after the access-control and "
                         "privacy paragraph and before the render paragraph.",
                "find": None,
                "insert": True,
                "replace": [
                    "Validation tests check the data-entry rules that protect the quality of the records. The "
                    "email tests confirm that an email address cannot be a telephone number, that malformed "
                    "addresses are rejected, that an address ending in a plausible but non-existent "
                    "top-level domain is refused while a real domain is accepted and a suggestion naming the "
                    "likely intended domain is offered, and that a duplicate address cannot register a "
                    "second account - including where the two differ only in letter case - while an address "
                    "released by a deactivated account becomes available again. The Ghanaian telephone tests "
                    "confirm that every valid network prefix is accepted and its network identified; that "
                    "numbers longer than nine digits, numbers in the legacy leading-zero form, numbers "
                    "containing letters and numbers with an unknown prefix are rejected; that spaces, dashes "
                    "and parentheses are tolerated and normalised to a canonical international form; and that "
                    "the same number cannot be registered twice. The same rules are verified in the model "
                    "fields and on the hospital and donor forms as well as the main registration form, so "
                    "that a value which reaches the database by another route still cannot be invalid. The "
                    "password-checklist tests confirm that the live feedback beside the password field "
                    "agrees with the configured validators, and the expiry-wording tests confirm that the "
                    "reset email, the confirmation page and the invalid-link page all state the configured "
                    "twelve-hour expiry.",
                    "Delivery tests cover the mechanisms that operate outside the application. The "
                    "password-reset routing tests confirm that the link is addressed only to the matching "
                    "account and that an unregistered address produces no message at all. The SMTP tests "
                    "confirm that a stalled connection is retried until it succeeds, that the backend gives "
                    "up after four attempts and re-raises the error, that a rejected authentication is not "
                    "retried, and that a retry cleans up the part of the connection it has opened. The HTTPS "
                    "mail backend tests confirm that the request payload matches the provider's API "
                    "contract, that a display name is parsed out of the sender header, that copy, blind-copy "
                    "and reply-to headers are forwarded, that unreachable servers and rate-limited and "
                    "server-error responses are retried while authentication, budget and malformed-payload "
                    "errors are not, that a timeout is treated as a retryable failure, and that an empty "
                    "recipient list is rejected before any request is made. Failure-path tests confirm that a "
                    "message which cannot be sent is logged without raising, that a batch continues after "
                    "one dead message, and that a notification is still stored in the application even when "
                    "its email cannot be delivered, so that a mail outage can never roll back or break the "
                    "action that triggered the notification."
                ],
            },
            {
                "where": "Section 4.1.3, inside the workflow-tests paragraph (the end-to-end sentence).",
                "find": "staff record a donation, which creates an available blood bag;",
                "replace": [
                    "staff record a donation, which creates an untested blood bag, and the laboratory "
                    "screening that follows clears it into the available pool;"
                ],
            },
        ],
    },
    {
        "title": "3.  Section 4.1.3 - corrected Table 4.2",
        "lead": "The printed table listed 28 classes whose figures sum to 120, against a stated total of 110; "
                "six of its rows no longer match the code and nineteen classes were missing altogether. The "
                "table below is the verified replacement: 47 classes, 264 tests, totals row included so an "
                "examiner can check the arithmetic. Replace the whole table rather than individual rows, and "
                "keep the caption \"Table 4.2: Summary of test results by module\".",
        "items": [],
        "table": {
            "header": TABLE_42_HEADER,
            "rows": [list(r) + ["All passed"] for r in TABLE_42_ROWS],
            "total": list(TABLE_42_TOTAL) + ["All passed"],
        },
    },
    {
        "title": "4.  The laboratory screening gate in the requirements (Section 3.2.3)",
        "lead": "The document describes a blood bag as becoming available the moment a donation is recorded, "
                "and lists five bag statuses. The implemented system creates every bag untested and releases "
                "it only after the laboratory has reported on all four markers of the infection panel. The "
                "text below brings the requirements into line.",
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
                    "(HIV, hepatitis B, hepatitis C and syphilis). A unit for which any marker is reactive "
                    "shall be discarded, with the reactive markers recorded as the reason, and the donor "
                    "shall be notified and advised to seek counselling and confirmatory testing."
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
                    "bag: the bag shall become available only when every result is non-reactive, and shall be "
                    "discarded when any result is reactive, with the reactive markers recorded and the donor "
                    "notified. A screening that has been completed shall not be entered a second time."
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
                "where": "Section 3.2.3, inside the \"Blood requests and matching\" requirement - add this "
                         "sentence after the sentence describing first-expiry-first-out reservation.",
                "find": None,
                "replace": [
                    "Only bags that have passed the laboratory screening gate shall be eligible for "
                    "reservation; a unit that is still awaiting the laboratory shall not be offered to a "
                    "request."
                ],
            },
        ],
    },
    {
        "title": "5.  The laboratory screening gate in the data design (Section 3.3)",
        "lead": "Two tables are missing from the database section - the screening record for each donation and "
                "the appointment record - so the count of tables and two descriptions change.",
        "items": [
            {
                "where": "Section 3.3.2, opening sentence of the database description.",
                "find": "a relational database containing eleven tables",
                "replace": ["a relational database containing thirteen tables"],
            },
            {
                "where": "Section 3.3.2, the sentence describing the BloodBag table.",
                "find": "current status (available, reserved, issued, expired or discarded)",
                "replace": ["current status (untested, available, reserved, issued, expired or discarded)"],
            },
            {
                "where": "Section 3.3.2 - new sentences, inserted after the paragraph describing the "
                         "Donation, BloodBag and BloodRequest tables.",
                "find": None,
                "insert": True,
                "replace": [
                    "The laboratory screening of each donation is held in its own table, linked one-to-one to "
                    "the donation, which stores one result for each marker of the infection panel, the staff "
                    "member who entered the results, the time of entry and the reason recorded when a unit is "
                    "discarded. A bag is created untested, and it is this record that decides whether the bag "
                    "enters the available pool or is discarded.",
                    "An Appointment table records a donor's request to donate at a chosen hospital on a "
                    "proposed date, together with the donor's note, the hospital's decision and note, and the "
                    "time of the decision, so that a booking is a tracked record shared by both sides rather "
                    "than an untracked telephone call.",
                ],
            },
            {
                "where": "Chapter Three summary (the paragraph beginning \"This chapter has analysed the "
                         "problem\").",
                "find": "the design of the eleven-table database",
                "replace": ["the design of the thirteen-table database"],
            },
        ],
    },
    {
        "title": "6.  The laboratory screening gate in Chapter Four - the phases",
        "lead": "Phase 2 ends with a bag appearing in inventory and Phase 3 describes expiry over \"available\" "
                "bags only. Both passages are replaced below.",
        "items": [
            {
                "where": "Section 4.1.2, replace the whole Phase 2 paragraph.",
                "find": None,
                "replace": [
                    "Phase 2: Donor Screening and Donation Recording. The second phase implemented the "
                    "two-stage screening process and the recording of donations. When hospital staff select "
                    "an approved donor for screening, the system first runs the stage-one eligibility check, "
                    "which evaluates the donor's age, weight and the interval since the last donation against "
                    "the thresholds configured in the application (see Table 3.2 in Chapter Three). The "
                    "stage-one check returns one of three outcomes: eligible, temporarily deferred, or "
                    "permanently ineligible. Hospital staff then enter the donor's haemoglobin level and "
                    "blood pressure readings for the stage-two clinical screening. The combined outcome of "
                    "both stages is recorded as a screening record, and the donor is notified. Recording a "
                    "donation enforces eligibility at the point of action: the system checks that the donor's "
                    "registration is approved, that a recent screening exists with an eligible outcome, and "
                    "that the required interval since the last donation has elapsed. A successful recording "
                    "creates a donation record and a corresponding blood bag in the hospital's inventory, "
                    "with the expiry date computed as the collection date plus the configured shelf life of "
                    "thirty-five days. The new bag is created in the untested state and the laboratory "
                    "screening record for the donation is opened at the same moment, so that no unit can "
                    "enter the stock pool before the laboratory has cleared it. The member of staff who "
                    "recorded the donation is taken straight to the laboratory screening queue, which lists "
                    "the hospital's donations awaiting screening oldest first. Entering the four results - "
                    "HIV, hepatitis B, hepatitis C and syphilis - completes the screening: when every result "
                    "is non-reactive the bag becomes available and enters the stock pool, and when any result "
                    "is reactive the bag is discarded, with the reactive markers recorded as the reason, and "
                    "the donor is notified and advised to seek counselling and confirmatory testing. While "
                    "the screening is incomplete the bag is visible in the hospital's inventory but is "
                    "excluded from the stock figures and cannot be reserved. A unit that reaches its expiry "
                    "date before the laboratory clears it is marked expired instead of being released."
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
                    "attention. A daily management command scans every bag that has not reached a final state "
                    "- untested, available and reserved - and changes the status of any bag whose expiry date "
                    "has passed to expired, recording the event in the audit log and sending a low-stock "
                    "notification to the hospital's staff when the available stock of any blood group falls "
                    "below the configured threshold."
                ],
            },
            {
                "where": "Section 4.1.2, Phase 4 - add this sentence at the end of the sentence describing "
                         "the patient's request.",
                "find": "The patient submits a request specifying the blood group, the number of units and "
                        "the urgency (routine, urgent or emergency), and the request enters a pending state.",
                "replace": [
                    "The patient submits a request specifying the blood group, the number of units and the "
                    "urgency (routine, urgent or emergency), and the request enters a pending state. Only "
                    "bags that have cleared laboratory screening take part in the matching that follows."
                ],
            },
        ],
    },
    {
        "title": "7.  Section 4.2.1 - corrected Table 4.3 (evaluation criteria)",
        "lead": "The evaluation table needs the same new evidence as Table 4.2: the laboratory gate, and the "
                "validation and reset-security suites. Note also that its caption currently reads \"Table 4.2\" "
                "- it should read \"Table 4.3: Evaluation criteria and supporting test evidence\", since Table "
                "4.2 is the test-results table above it. Replace the whole table with the rows below.",
        "items": [],
        "table": {"header": TABLE_43_HEADER, "rows": [list(r) for r in TABLE_43_ROWS], "total": None},
    },
    {
        "title": "8.  Smaller corrections confirmed in the same audit",
        "lead": "These three are not about the test count or the laboratory gate, but they are wrong in the "
                "current file and are fixed by the same editing pass. (The cross-reference in the paragraph "
                "above the evaluation table already reads \"Table 4.3 maps each objective...\", so once the "
                "caption is corrected the two agree.)",
        "items": [
            {
                "where": "Section 3.3.6, Session and password security.",
                "find": "Password reset links expire after one day.",
                "replace": ["Password reset links expire after twelve hours."],
            },
            {
                "where": "Section 4.2 - the second heading numbered 4.2.3.",
                "find": "4.2.3   Performance Evaluation",
                "replace": ["4.2.4   Performance Evaluation"],
            },
            {
                "where": "The caption above the evaluation table in Section 4.2.1.",
                "find": "Table 4.2: Evaluation criteria and supporting test evidence",
                "replace": ["Table 4.3: Evaluation criteria and supporting test evidence"],
            },
        ],
    },
    {
        "title": "9.  Optional but recommended: the appointment feature has no counterpart in the document",
        "lead": "Table 4.2 now carries a row for AppointmentTests (15 tests) and DonationSitesTests (8 tests), "
                "yet Chapter Three records no such requirement and Chapter Four describes no such page, and "
                "the Appointment table is missing from the database section. The three passages below close "
                "that gap; they are the reason the appointment tests exist, so an examiner who reads the "
                "table will look for them.",
        "items": [
            {
                "where": "Section 3.2.3 - new requirement paragraph, inserted after \"Donation recording\" and "
                         "\"Laboratory screening\".",
                "find": None,
                "insert": True,
                "replace": [
                    "Donation appointments: A donor shall be able to see the hospitals that are open to "
                    "donations, the blood groups each hospital holds in available stock, and the groups in "
                    "which it is short, and shall be able to book a visit to a chosen hospital on a proposed "
                    "date. The hospital's staff shall be able to confirm or decline the booking with a note, "
                    "and the donor shall see the outcome and be able to cancel a booking that is still "
                    "pending. A booking shall be refused for a donor whose registration is not approved, for "
                    "a hospital that is not visible to donors, for a date in the past or beyond the "
                    "permitted booking window, and where the donor already holds a pending booking at that "
                    "hospital."
                ],
            },
            {
                "where": "Section 4.2.3 - new feature paragraph for the user-interface walkthrough, with a "
                         "screenshot (the donation sites directory) as Figure 4.10.",
                "find": None,
                "insert": True,
                "replace": [
                    "WHERE TO DONATE (DONATION SITES AND APPOINTMENTS)",
                    "The donation sites directory shows the hospitals that are open to donors, with the "
                    "blood groups each one currently holds and the groups that have fallen below the "
                    "low-stock threshold, so that a donor can see where a donation is most needed. Hospitals "
                    "in the donor's own city are ranked first, and within a city the hospitals that are short "
                    "of the donor's own blood group come first, carrying a badge that marks the need. Each "
                    "entry offers a booking control, and booking an appointment creates a pending record "
                    "that the hospital's staff see in their appointment inbox, where they can confirm the "
                    "visit or decline it with a note; the donor sees the decision in their own appointment "
                    "list and can cancel a booking that has not yet been decided. The directory, the booking "
                    "form, the donor's appointment list and the staff inbox are exercised by the appointment "
                    "and donation-site tests described in Section 4.1.3."
                ],
            },
            {
                "where": "Section 3.3.2 - the appointment sentence supplied in section 5 above already covers "
                         "the table itself; if you prefer to keep the data design in one place, add it there "
                         "instead of here.",
                "find": None,
                "insert": True,
                "replace": [
                    "An Appointment table records a donor's request to donate at a chosen hospital on a "
                    "proposed date, together with the donor's note, the hospital's decision and note, and "
                    "the time of the decision."
                ],
            },
        ],
    },
]


# --------------------------------------------------------------------------- #
# Markdown renderer
# --------------------------------------------------------------------------- #
def md_table(header, rows, total=None) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    if total:
        out.append("| " + " | ".join(f"**{c}**" for c in total) + " |")
    return "\n".join(out)


def render_markdown() -> str:
    parts = [
        "# CBODS_NEW V7.2 - corrected replacement text",
        "",
        "Covers the test count (264 tests in 47 classes), the missing test classes, and the laboratory "
        "screening gate. Nothing here has been written into `CBODS_NEW V7.2.docx`; every item names the "
        "passage it replaces and quotes the existing sentence so it can be located with Find.",
        "",
        "Counts verified by running the suite (`manage.py test`: Found 264 test(s), OK) and by counting "
        "test methods per class in the source tree.",
        "",
    ]
    for sec in SECTIONS:
        parts += [f"## {sec['title']}", "", sec["lead"], ""]
        for item in sec["items"]:
            parts += [f"**Where: {item['where']}**", ""]
            if item.get("find"):
                parts += [f"*Find:* {item['find']}", ""]
            if item.get("insert"):
                parts += ["*New paragraph - insert at the position named above:*", ""]
            for i, para in enumerate(item["replace"]):
                label = "*Replacement text:* " if i == 0 else "*Continuation:* "
                parts += [label + para, ""]
        if sec.get("table"):
            t = sec["table"]
            parts += [md_table(t["header"], t["rows"], t.get("total")), ""]
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
        ("" if i == 0 else '<w:r><w:br/></w:r>')
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


def cell(text, *, bold=False, shade=None, width=None, size=18) -> str:
    tcpr = "<w:tcPr>"
    if width:
        tcpr += f'<w:tcW w:w="{width}" w:type="dxa"/>'
    if shade:
        tcpr += f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
    tcpr += "</w:tcPr>"
    p = para(text, bold=bold, size=size, space_after=40)
    return f"<w:tc>{tcpr}{p}</w:tc>"


def table(header, rows, total=None, widths=None) -> str:
    n = len(header)
    widths = widths or [1200] * n
    grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)
    borders = (
        "<w:tblBorders>"
        + "".join(
            f'<w:{edge} w:val="single" w:sz="6" w:space="0" w:color="999999"/>'
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV")
        )
        + "</w:tblBorders>"
    )
    tblpr = (
        f'<w:tblPr><w:tblW w:w="{sum(widths)}" w:type="dxa"/>{borders}'
        '<w:tblLayout w:type="fixed"/></w:tblPr>'
    )
    out = [f"<w:tbl>{tblpr}<w:tblGrid>{grid}</w:tblGrid>"]
    hdr = "<w:tr><w:trPr><w:tblHeader/></w:trPr>"
    hdr += "".join(cell(h, bold=True, shade="E8E8E8", width=w) for h, w in zip(header, widths))
    out.append(hdr + "</w:tr>")
    for r in rows:
        out.append("<w:tr>" + "".join(cell(c, width=w) for c, w in zip(r, widths)) + "</w:tr>")
    if total:
        out.append(
            "<w:tr>"
            + "".join(cell(c, bold=True, shade="F4F4F4", width=w) for c, w in zip(total, widths))
            + "</w:tr>"
        )
    out.append("</w:tbl>")
    return "".join(out)


def render_docx() -> bytes:
    body = []
    body.append(para("CBODS_NEW V7.2 - corrected replacement text", bold=True, size=32, space_after=120,
                     keep_next=True))
    body.append(para("Test counts (264 tests in 47 classes), the missing test classes, and the laboratory "
                     "screening gate", italic=True, size=22, color="555555", space_after=200))
    body.append(para("How to use this document: each item names the passage to change and quotes the "
                     "existing sentence. Replacement paragraphs are set in Times New Roman 12 pt, "
                     "justified, exactly like the body of the thesis, so they can be copied and pasted "
                     "without reformatting. Table 4.2 and Table 4.3 below are real Word tables - select "
                     "the whole table and paste it over the old one. Nothing in this file has been "
                     "written into CBODS_NEW V7.2.docx.", size=21, color="333333", justify=True,
                     space_after=240))
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
                body.append(label("(new paragraph - insert at the position named above)"))
            for p in item["replace"]:
                body.append(para(p, justify=True, space_after=200))
        if sec.get("table"):
            t = sec["table"]
            widths = [1300, 2600, 900, 3500, 900] if len(t["header"]) == 5 else [1900, 2400, 5300]
            body.append(table(t["header"], t["rows"], t.get("total"), widths))
            body.append(para("", space_after=120))
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
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)
    return buf.getvalue()


def main() -> None:
    total = sum(int(r[2]) for r in TABLE_42_ROWS)
    assert len(TABLE_42_ROWS) == 47, len(TABLE_42_ROWS)
    assert total == 264, total
    OUT_MD.write_text(render_markdown(), encoding="utf-8")
    OUT_DOCX.write_bytes(render_docx())
    print(f"{OUT_MD}  ({OUT_MD.stat().st_size} bytes)")
    print(f"{OUT_DOCX}  ({OUT_DOCX.stat().st_size} bytes)")
    print(f"Table 4.2: {len(TABLE_42_ROWS)} classes, {total} tests")


if __name__ == "__main__":
    main()
