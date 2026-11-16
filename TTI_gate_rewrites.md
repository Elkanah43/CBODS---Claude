# CBODS_NEW V7.2 - TTI laboratory gate rewrites (Chapters 3 and 4)

Rewrites every passage describing donation recording or blood bag statuses so that the UNTESTED -> AVAILABLE flow is stated consistently: requirements (3.2.3), data design (3.3.2), workflow diagrams (3.3.3), security (3.3.6), the chapter summary, the phase narrative (4.1.2) and the test narrative (4.1.3, 4.2.2, 4.2.4). Nothing here has been written into `CBODS_NEW V7.2.docx`.

Note: items A1, A2, A3, E1 and E2 are the same rewrites as sections 4-6 of `CBODS_CORRECTIONS.docx`; the other items here are additional passages that document did not cover.

## How to use this rewrite set

This document rewrites every passage in Chapters Three and Four that describes donation recording or blood bag statuses, so that the laboratory screening gate - every bag is born untested and becomes available only after all four TTI markers are non-reactive - is stated consistently from the requirements through the data design, the workflow diagrams and the implementation narrative. Each item names the passage and quotes the sentence to locate with Find; replacement paragraphs are set like the thesis body. If you have already applied sections 4-6 of CBODS_CORRECTIONS.docx, its donation-recording, laboratory-screening, inventory-management, Phase 2 and Phase 3 rewrites are the same text as items A1, A2, A3, E1 and E2 here - apply those once, and use the remaining items here for the passages that document did not cover.

## A.  Section 3.2.3 - the functional requirements

The requirements currently describe a bag that becomes available the moment a donation is recorded, and a status list with no untested state. Three requirements change and one is new.

**Where: Section 3.2.3, replace the whole "Donation recording" requirement.**

*Replacement text:* Donation recording: Hospital staff shall be able to record a completed donation for an eligible donor. The system shall enforce eligibility at the time of recording, so that a donation cannot be recorded for a donor whose registration is not approved, who has no recent eligible screening, or who has not yet waited the required interval. Each recorded donation shall create a corresponding blood bag in the hospital's inventory with a computed expiry date, and shall open a laboratory screening record for that donation. The new bag shall be created in the untested state, and shall not be counted in stock, offered to a request or issued until the laboratory has recorded a non-reactive result for every marker of the transfusion-transmissible infection panel (HIV, hepatitis B, hepatitis C and syphilis).

**Where: Section 3.2.3 - new requirement paragraph, inserted immediately after "Donation recording".**

*New sentences - insert at the position named above:*

*Replacement text:* Laboratory screening: Hospital staff shall be able to enter the laboratory results for a recorded donation, one result for each marker of the transfusion-transmissible infection panel - HIV, hepatitis B, hepatitis C and syphilis. All four results shall be required before the screening is treated as complete, and an incomplete screening shall neither release nor discard the unit. The outcome of the screening shall gate the blood bag: the bag shall move from untested to available only when every result is non-reactive, and shall be discarded when any result is reactive, with the reactive markers recorded as the reason and the donor notified and advised to seek counselling and confirmatory testing. A screening that has been completed shall not be entered a second time, and a unit that reaches its expiry date before the laboratory clears it shall be marked expired rather than released.

**Where: Section 3.2.3, replace the whole "Inventory management" requirement.**

*Replacement text:* Inventory management: The system shall maintain, for each registered hospital, a record of every blood bag and its status. The possible statuses of a bag are untested, available, reserved, issued, expired and discarded, and a bag that has just been recorded begins as untested. The system shall calculate stock levels from the available bags rather than storing a separate counter, so that the displayed stock is always consistent with the underlying records; units awaiting the laboratory shall be visible to hospital staff but excluded from the stock figures and unavailable for reservation. It shall identify bags that are close to their expiry date, mark bags that have passed their expiry date - including bags still awaiting the laboratory - and notify hospital staff when the available stock of any blood group falls below a defined threshold.

**Where: Section 3.2.3, "Blood requests and matching" requirement - add this sentence at the end of the requirement.**

*Find:* Where an emergency request cannot be met from available stock, the system shall send an urgent broadcast notification to the compatible donors registered in the hospital's city.

*Replacement text:* Where an emergency request cannot be met from available stock, the system shall send an urgent broadcast notification to the compatible donors registered in the hospital's city. Only bags that have passed the laboratory screening gate shall be eligible for reservation; a unit that is still untested shall not appear in the stock a request can draw on.

**Where: Section 3.2.3 (non-functional requirements), "Reliability" - add this sentence at the end.**

*Find:* The system shall prevent a bag from being reserved or issued twice, even when two users act at the same time.

*Replacement text:* The system shall prevent a bag from being reserved or issued twice, even when two users act at the same time. The release of a screened unit into the available pool, the discarding of a reactive unit and the expiry of a past-date unit shall each be applied through a single audited code path, so that a status change and its audit entry cannot be recorded separately.

## B.  Section 3.3.2 - the data design

The database section counts eleven tables, describes the bag statuses without the untested state, and holds no laboratory screening record. The table count, the BloodBag description and the design-decision paragraph all change, and two sentences are added.

**Where: Section 3.3.2, opening sentence of the database description.**

*Find:* The database that supports CBODS is a relational database containing eleven tables, and its structure follows directly from the workflows described in the functional requirements.

*Replacement text:* The database that supports CBODS is a relational database containing thirteen tables, and its structure follows directly from the workflows described in the functional requirements.

**Where: Section 3.3.2, in the paragraph on donor management - replace the sentence describing the BloodBag table.**

*Find:* The BloodBag table represents a single unit of donated blood and stores its blood group, volume, collection date, expiry date (computed as the collection date plus thirty-five days), current status (available, reserved, issued, expired or discarded), the donation from which it was created, and if the bag has been allocated the blood request for which it is reserved.

*Replacement text:* The BloodBag table represents a single unit of donated blood and stores its blood group, volume, collection date, expiry date (computed as the collection date plus thirty-five days), current status (untested, available, reserved, issued, expired or discarded), the donation from which it was created, and if the bag has been allocated the blood request for which it is reserved. Every bag is created in the untested state, and it is the laboratory screening record described below that decides when it may enter the available pool.

**Where: Section 3.3.2 - two new sentences, inserted at the end of the same paragraph (after the OrganDonationRequest description).**

*New sentences - insert at the position named above:*

*Replacement text:* The laboratory screening of each donation is held in its own table, linked one-to-one to the donation, which stores one result for each marker of the infection panel, the staff member who entered the results, the time of entry and the reason recorded when a unit is discarded. The record is kept after the decision, so that the reason a unit was discarded survives alongside the audit trail. An Appointment table records a donor's request to donate at a chosen hospital on a proposed date, together with the donor's note, the hospital's decision and note, and the time of the decision.

**Where: Section 3.3.2, the paragraph on design decisions - add this sentence at the end.**

*Find:* This design was chosen deliberately, because in a real hospital two staff members could act on the same request or the same stock at almost the same moment, and the system must behave correctly in that situation.

*Replacement text:* This design was chosen deliberately, because in a real hospital two staff members could act on the same request or the same stock at almost the same moment, and the system must behave correctly in that situation. A further decision concerns the safety gate: every change to a bag's status passes through a single service function, so that a unit cannot reach the available, reserved or discarded state without the change and its reason being written to the audit log at the same moment.

## C.  Section 3.3.3 - the matching component and the workflow diagrams

The request-lifecycle narrative assumes the pool it draws from is the available stock; each passage below is tightened so that the pool is explicitly the set of laboratory-cleared units.

**Where: Section 3.3.3, the paragraph describing the matching component - add this sentence at the end.**

*Find:* For emergency requests, donors who can donate immediately are ranked first, because the need is immediate.

*Replacement text:* For emergency requests, donors who can donate immediately are ranked first, because the need is immediate. The pool of bags against which the component matches is the set of units that have passed the laboratory screening gate; a unit still awaiting the laboratory is invisible to the matching process, however recently it was collected.

**Where: Section 3.3.3, the sequence-diagram walkthrough (acceptance transaction) - replace the quoted clause.**

*Find:* Within this transaction, the required number of compatible bags are located in first-expiry-first-out order, each bag is linked to the request and its status is changed from available to reserved, and the request status is updated to accepted.

*Replacement text:* Within this transaction, the required number of compatible bags are located in first-expiry-first-out order among the units that have passed the laboratory screening gate, each bag is linked to the request and its status is changed from available to reserved, and the request status is updated to accepted.

**Where: Section 3.3.3, the Figure 3.6 flowchart description - replace the quoted clause.**

*Find:* the system enters an atomic transaction that locks the request row, locates compatible bags in first-expiry-first-out order, reserves them and updates the request status to accepted

*Replacement text:* the system enters an atomic transaction that locks the request row, locates compatible bags in first-expiry-first-out order among the units cleared by the laboratory screening gate, reserves them and updates the request status to accepted

**Where: Section 3.3.3, the Figure 3.5 data-flow description - replace the quoted sentence.**

*Find:* When a donation is completed, the Donation Recording and Inventory Management process creates a Blood Bag Inventory record linked to the donor and the hospital.

*Replacement text:* When a donation is completed, the Donation Recording and Inventory Management process creates a Blood Bag Inventory record linked to the donor and the hospital in the untested state, together with a laboratory screening record; the unit joins the available stock in that store only once the screening results have been entered and every marker is non-reactive, and a reactive unit is discarded instead.

*Note:* If Figure 3.5 is redrawn, add a Laboratory Screening process between Donation Recording and the inventory store; the wording above also stands against the present figure.

## D.  Section 3.3.6 and the Chapter Three summary

The audit-trail requirement should name the gate explicitly, and the chapter summary should list it among the safety measures.

**Where: Section 3.3.6, "Audit trail" - replace the quoted sentence.**

*Find:* This includes the approval and rejection of donors, the creation and status changes of blood bags, the acceptance, rejection and fulfilment of requests, and the progress of organ donation requests.

*Replacement text:* This includes the approval and rejection of donors, the creation of blood bags in the untested state and every subsequent change of their status, the entry of laboratory screening results and the release or discard of the units they decide, the acceptance, rejection and fulfilment of requests, and the progress of organ donation requests.

**Where: Chapter Three summary, the sentence listing the security measures - replace the quoted ending.**

*Find:* centred on role-based access control, the restricted handling of identity documents, privacy-aware queries, session and password security, and a complete audit trail.

*Replacement text:* centred on role-based access control, the restricted handling of identity documents, privacy-aware queries, session and password security, the laboratory screening gate that holds every donated unit out of the usable stock until it is cleared, and a complete audit trail.

## E.  Chapter Four - the implementation narrative

Phase 2 ends with a bag simply appearing in inventory, Phase 3 expires only "available" bags, and both test descriptions show the bag becoming available at the moment of recording. Five passages change.

**Where: Section 4.1.2, replace the whole Phase 2 paragraph.**

*Replacement text:* Phase 2: Donor Screening and Donation Recording. The second phase implemented the two-stage screening process and the recording of donations. When hospital staff select an approved donor for screening, the system first runs the stage-one eligibility check, which evaluates the donor's age, weight and the interval since the last donation against the thresholds configured in the application (see Table 3.2 in Chapter Three). The stage-one check returns one of three outcomes: eligible, temporarily deferred, or permanently ineligible. Hospital staff then enter the donor's haemoglobin level and blood pressure readings for the stage-two clinical screening. The combined outcome of both stages is recorded as a screening record, and the donor is notified. Recording a donation enforces eligibility at the point of action: the system checks that the donor's registration is approved, that a recent screening exists with an eligible outcome, and that the required interval since the last donation has elapsed. A successful recording creates a donation record and a corresponding blood bag in the hospital's inventory, with the expiry date computed as the collection date plus the configured shelf life of thirty-five days. The new bag is created in the untested state, and the laboratory screening record for the donation is opened at the same moment, so that no unit can enter the stock pool before the laboratory has cleared it. The member of staff who recorded the donation is taken straight to the laboratory screening queue, which lists the hospital's donations awaiting screening oldest first. Entering the four results - HIV, hepatitis B, hepatitis C and syphilis - completes the screening: when every result is non-reactive the bag moves from untested to available and enters the stock pool, and when any result is reactive the bag is discarded, with the reactive markers recorded as the reason, and the donor is notified and advised to seek counselling and confirmatory testing. While the screening is incomplete the bag is visible in the hospital's inventory but is excluded from the stock figures and cannot be reserved, and a unit that reaches its expiry date before the laboratory clears it is marked expired instead of being released.

**Where: Section 4.1.2, replace the whole Phase 3 paragraph.**

*Replacement text:* Phase 3: Blood Bag Inventory and Expiry Tracking. The third phase added the inventory dashboard and the expiry tracking mechanism. The inventory is displayed on a per-hospital basis, with stock levels for each blood group computed from the available bags rather than stored as a separate counter. This design ensures that the displayed stock is always consistent with the underlying records. Units awaiting laboratory screening are shown separately from the available stock, so that hospital staff can see what is still in the laboratory without it being counted as usable blood. The system identifies bags that are within seven days of their expiry date and highlights them for attention. A daily management command scans every bag that has not yet reached a final state - untested, available and reserved alike - and changes the status of any bag whose expiry date has passed to expired, recording the event in the audit log and sending a low-stock notification to the hospital's staff when the available stock of any blood group falls below the configured threshold.

**Where: Section 4.1.2, Phase 4 - add this sentence at the end of the paragraph.**

*Find:* When an emergency request cannot be met from available stock, the system sends an urgent broadcast notification to compatible donors registered in the hospital's city, and presents hospital staff with a ranked list of compatible donors, rioritizing those who can donate immediately.

*Replacement text:* When an emergency request cannot be met from available stock, the system sends an urgent broadcast notification to compatible donors registered in the hospital's city, and presents hospital staff with a ranked list of compatible donors, prioritizing those who can donate immediately. Only bags that have cleared laboratory screening take part in the reservation that follows; the matching and reservation code never sees a unit that is still untested.

**Where: Section 4.1.3, inside the workflow-tests paragraph (the end-to-end sentence) - replace the quoted clause.**

*Find:* staff record a donation, which creates an available blood bag;

*Replacement text:* staff record a donation, which creates an untested blood bag, and enter laboratory screening results that clear the bag into the available pool;

**Where: Section 4.2.2, the end-to-end walkthrough chain - replace the quoted chain.**

*Find:* donor registration -> administrator approval -> screening -> donation recording -> patient blood request -> acceptance and reservation -> fulfilment and notification -> emergency broadcast -> organ donation request -> hospital approval -> administrator dashboard and audit log verification

*Replacement text:* donor registration -> administrator approval -> screening -> donation recording -> laboratory screening clears the unit -> patient blood request -> acceptance and reservation -> fulfilment and notification -> emergency broadcast -> organ donation request -> hospital approval -> administrator dashboard and audit log verification

**Where: Section 4.2.4, "Consistency" - add this sentence at the end.**

*Find:* The age of a donor is derived from the date of birth, and the interval since the last donation is derived from the donation records, so no cached value can drift out of step with the data it summarises.

*Replacement text:* The age of a donor is derived from the date of birth, and the interval since the last donation is derived from the donation records, so no cached value can drift out of step with the data it summarises. The same discipline applies to the laboratory gate: an untested unit is excluded from the stock computation by the same query that counts the available bags, so a unit awaiting the laboratory can never appear as usable stock.
