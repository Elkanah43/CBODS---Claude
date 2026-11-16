# CBODS_NEW V7.2 - Key Features entry: donor appointments

A new Section 4.2.3 entry in the style of the existing ones (Figure caption, ALL-CAPS page title, walkthrough paragraphs). Nothing here has been written into `CBODS_NEW V7.2.docx`.

**Placement:** Insert this entry at the end of Section 4.2.3 (Key Features and Interface Implementation), immediately after the HOSPITAL REPORT entry and before the Performance Evaluation heading. Take a screenshot of the donation sites directory (signed in as an approved donor) for the figure. If you have already applied section 9 of CBODS_CORRECTIONS.docx, its interface paragraph is an earlier draft of the same entry - use this version instead, and keep its requirement and data-design paragraphs.

**Figure 4.10: Donation sites directory and appointment booking**

### WHERE TO DONATE (DONATION SITES AND APPOINTMENTS)

The donation sites directory is the page an approved donor uses to decide where to give blood. It lists the hospitals that are open to donations, and beside each hospital it shows the blood groups that hospital currently holds in available stock, with the groups that have fallen below the low-stock threshold flagged. The list is ordered so that it answers two questions at once: hospitals in the donor's own city are ranked first, and within that group the hospitals that are short of the donor's own blood group come first, carrying a badge that marks the need. A donor can therefore see both where they can go and where they would be most useful. Eligibility is not decided on this page: the directory is informational, and the standing eligibility rules are still applied by hospital staff at the time of screening.

From the directory the donor can book a visit. The booking form asks for the day the donor proposes to come in and an optional note for the hospital, and it accepts only a date between today and sixty days ahead. A booking is refused unless the donor's registration has been approved, and a donor who already holds a pending booking at the same hospital is shown that booking instead of being offered a second one. When the booking is created, the staff of the chosen hospital are notified immediately, with the donor's name and blood group in the message, and the appointment enters a pending state that both sides can see.

Hospital staff review bookings in their appointment inbox, which lists the hospital's appointments newest first with a count of those still pending. Staff either confirm a booking or decline it with a note, and the donor is notified of the decision either way; the confirmation message reminds the donor to bring their government identity document. A donor can cancel a booking that has not yet been decided, which closes the appointment and tells the hospital's staff. Every step of the workflow - the booking, the cancellation, the confirmation and the decline - is recorded in the audit log with the actor and the date, so the appointment record gives both sides a shared status instead of an untracked telephone call. The directory, the booking form, the donor's appointment list and the staff inbox are exercised by the appointment and donation-site tests described in Section 4.1.3 (DonationSitesTests and AppointmentTests).

## Related one-line edits

**Where: The List of Figures (front matter) - add this line after the Figure 4.9 entry.**

Figure 4.10: Donation sites directory and appointment booking

**Where: Section 4.1.2, Phase 1 (or Phase 5) - one sentence recording when the feature was built, so the phase narrative and the interface walkthrough agree.**

The same phase added the donor-facing donation sites directory, from which an approved donor can book a donation appointment at a chosen hospital for staff to confirm or decline.

**Where: Section 4.1.3 - one sentence appended to the workflow-tests paragraph, so the test narrative covers the feature shown in Figure 4.10.**

The appointment tests book a visit from the donation sites directory, verify that an unapproved donor and a hidden hospital are refused, and confirm that hospital staff can confirm or decline the booking with the donor notified in each case.
