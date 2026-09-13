# CBODS — User Flow Comparison (NBSG vs CBODS)

Three sequence diagrams comparing how a donation actually happens under Ghana's
National Blood Service public workflow (nbs.gov.gh) and under CBODS. Rendered
by GitHub directly from the Mermaid sources below.

The key structural difference: **NBSG is broadcast-first** — the service
publishes a schedule, donors self-select, and every consequential step
(eligibility, confirmation, identification) is completed in person by staff.
**CBODS is transaction-first** — each of those steps is a recorded, audited
interaction inside the system, and CBODS adds the demand side (patient
requests matched to hospital stock) which NBSG's public flow leaves to phones
and walk-ins.

---

## 1. NBSG — donor journey (as published on nbs.gov.gh)

```mermaid
sequenceDiagram
    autonumber
    actor D as Prospective Donor
    participant W as NBSG Website
    participant S as NBSG Staff
    participant C as Blood Centre
    participant L as Laboratory and Distribution

    D->>W: Visit homepage, see weekly schedule and eligibility CTA
    D->>W: Take self-reported eligibility quiz
    W-->>D: Provisional result (final call rests with centre staff)
    D->>W: Browse weekly donation schedule (static and mobile clinics)
    D->>W: Register as donor and book appointment (Southern Zonal Blood Centre only)
    S->>D: Contact donor to confirm appointment
    opt Plans change
        D->>S: Ask to rearrange
    end
    D->>C: Arrive on the day with picture ID, complete registration form
    S->>D: Nurse screening (brief medical check) — final eligibility decided here
    alt Found eligible
        D->>C: Donate blood (10-15 minutes on donor bed)
        C-->>D: Rest and refreshment, learn blood type
        C->>L: Unit enters testing, component processing, storage, distribution (BSIS)
        opt Adverse reaction after donation
            D->>W: Share experience via the adverse-effect form
        end
        D->>W: Encouraged to sign up as repeat donor
    else Deferred
        S-->>D: Not eligible today, invited to try again later
    end
```

Reading notes:

- Steps 2–5 are **self-selected and unverified**: the quiz is honest-answer
  self-assessment, the booking is a single centre, and confirmation is a human
  callback rather than a tracked status.
- Identity is checked physically (picture ID at the desk) — there is no
  electronic ID verification before the donor arrives.
- Everything downstream of the needle (testing, processing, distribution) is
  the domain of BSIS, the blood service's internal information system — none of
  it is visible to the donor through the public site. CBODS models the first of
  these steps (TTI screening) as its laboratory gate; component processing and
  distribution remain out of scope.

---

## 2. CBODS — donor journey (registration to donation)

```mermaid
sequenceDiagram
    autonumber
    actor D as Donor
    participant S as CBODS System
    participant A as Admin
    participant H as Hospital Staff

    D->>S: Register with government ID upload (JPG/PNG/PDF, max 5 MB)
    S->>S: Application PENDING, ID stored outside MEDIA_ROOT, admin-only view
    A->>S: Review ID scan and details
    alt Approved
        A->>S: Approve registration
        S-->>D: Notification sent (email/console), profile unlocked
        D->>S: Open the Where to donate directory
        S-->>D: Hospitals listed, urgent-need badge on groups in short supply
        D->>S: Book appointment at chosen hospital (any hospital, not one centre)
        H->>S: Confirm or decline from the staff inbox
        S-->>D: Notified of the decision either way
        opt Donor changes mind while pending
            D->>S: Cancel booking
        end
        D->>H: Attend appointment
        H->>S: Stage 1 screening (age 18-60, weight 50 kg or more, 90-day interval)
        H->>S: Stage 2 screening (Hb 12.5 or more, BP 90-180 over 60-100)
        H->>S: Record donation
        S->>S: Create BloodBag as UNTESTED plus TTI record, expiry collected_date + 35 days
        S->>H: Laboratory TTI screening (HIV, hepatitis B, hepatitis C, syphilis)
        alt All markers non-reactive
            S->>S: Bag AVAILABLE, enters the stock pool
        else Reactive marker
            S->>S: Bag DISCARDED with reason recorded, donor notified for counselling
        end
        opt Organ donation offer
            D->>S: Offer an organ (kidney, liver, heart, lung, cornea, pancreas, skin)
            H->>S: Review and approve or reject
        end
    else Rejected
        A->>S: Reject with a written reason
        S-->>D: Reason shown to donor
        D->>S: Correct details and resubmit for review
    end
```

Reading notes:

- The 90-day interval between donations is **derived from recorded `Donation`
  rows**, not from donor memory — the same rule NBSG's quiz leaves to honesty.
- Every mandated action (approval, screening, booking, confirmation,
  cancellation, donation, bag creation) writes an `AuditLog` row.
- Booking is steered by live scarcity: hospitals short on the donor's blood
  group carry the "Book now — urgent need" button, so donors land where blood
  is scarcest. NBSG's schedule is static publication with no stock signal.

---

## 3. CBODS — patient request journey (the demand side NBSG's public flow lacks)

```mermaid
sequenceDiagram
    autonumber
    actor P as Patient
    participant S as CBODS System
    participant H as Hospital Staff
    actor D as Donor

    P->>S: Create blood request (group, units, urgency ROUTINE/URGENT/EMERGENCY)
    S->>S: Check compatibility rules and live availability (computed from AVAILABLE bags)
    alt Compatible units in stock
        H->>S: Reserve a bag (FEFO inside select_for_update)
        S->>S: Bag RESERVED for this request only, double-issue impossible
        H->>S: Issue the bag to the patient
        S->>S: Bag ISSUED, stock recomputed, action audited
        S-->>P: Request FULFILLED
    else Shortage
        S-->>P: Denied, with compatible alternatives listed
        S->>D: Emergency broadcast to matching available donors
        D->>S: Book appointment under the urgent-need flag
    end
    opt Daily maintenance
        S->>S: expire_bags marks past-expiry bags EXPIRED and fires low-stock alerts
    end
```

Reading notes:

- The NBSG public flow has **no patient-facing leg at all**: a patient's need
  travels by clinician referral and phone. In CBODS the request, the
  compatibility check, the reservation and the issue are all first-class
  recorded transactions.
- Reservation isolation (`BloodBag.reserved_for`) plus row locking means two
  staff can never fulfil two requests with the same bag — an integrity
  guarantee a paper or broadcast workflow cannot make.

---

## Step-by-step mapping

| NBSG step | CBODS equivalent | What changed |
|---|---|---|
| Self-reported eligibility quiz | Staff-recorded stage-1 screening | Honesty replaced by recorded data |
| Static weekly schedule publication | Live hospital directory ranked by shortage | Donors steered to scarcity |
| Book at one centre, confirmed by callback | Book at any hospital, confirmed in-app with tracked status | Human loop replaced by audited workflow |
| Picture ID checked at the desk | Government ID uploaded at registration, admin-gated | Verification happens before arrival |
| Nurse screening at the centre | Stage-2 ScreeningRecord (Hb, BP) with failed reasons | Outcome persisted, deferral history queryable |
| In-person lab TTI testing (BSIS domain) | TTITestRecord per donation, UNTESTED to AVAILABLE gate | Safety gate modelled; confirmatory testing out of scope |
| Adverse-effect sharing form | Not modelled | Known gap |
| Learn blood type after donation | Blood group on profile from registration | Known earlier, editable by donor |
| Offline testing/processing/distribution (BSIS) | Out of scope — one whole-blood bag per donation | Deliberate MVP boundary |
