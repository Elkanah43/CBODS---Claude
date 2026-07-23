# CBODS — Entity Relationship Diagram

Eleven models across eight Django apps. Rendered by GitHub directly from the
Mermaid source below.

```mermaid
erDiagram
    USER ||--o| DONOR : "registers as"
    USER ||--o| STAFFPROFILE : "works as"
    USER ||--o{ BLOODREQUEST : "requests as patient"
    USER ||--o{ DONATION : "records as staff"
    USER ||--o{ NOTIFICATION : receives
    USER ||--o{ AUDITLOG : "acts in"

    HOSPITAL ||--o{ STAFFPROFILE : employs
    HOSPITAL ||--o{ BLOODBAG : stores
    HOSPITAL ||--o{ DONATION : hosts
    HOSPITAL ||--o{ BLOODREQUEST : receives
    HOSPITAL ||--o{ ORGANDONATIONREQUEST : reviews

    DONOR ||--o{ SCREENINGRECORD : "screened by"
    DONOR ||--o{ DONATION : gives
    DONOR ||--o{ ORGANDONATIONREQUEST : offers

    DONATION ||--o{ BLOODBAG : yields
    BLOODREQUEST ||--o{ BLOODBAG : reserves

    USER {
        int id PK
        string username UK
        string email
        string password
        string role "ADMIN|DONOR|PATIENT|HOSPITAL_STAFF"
        string phone
        bool is_active
    }

    HOSPITAL {
        int id PK
        string name
        string city
        string address
        string phone
        text services_offered
        text organ_requirements
        bool is_hidden "hidden from non-admins"
    }

    STAFFPROFILE {
        int id PK
        int user_id FK "OneToOne"
        int hospital_id FK
    }

    DONOR {
        int id PK
        int user_id FK "OneToOne"
        string full_name
        date date_of_birth "age derived, never stored"
        string sex "M|F"
        string blood_group "A+|A-|B+|B-|AB+|AB-|O+|O-"
        decimal weight_kg
        string city
        string contact_phone "staff and admin only"
        text medical_history
        file id_document "admin-only gated view"
        string registration_status "PENDING|APPROVED|REJECTED"
        bool is_available
        text rejection_reason "nullable"
    }

    SCREENINGRECORD {
        int id PK
        int donor_id FK
        bool stage1_passed
        decimal hemoglobin_g_dl "nullable"
        int systolic_bp "nullable"
        int diastolic_bp "nullable"
        string outcome "ELIGIBLE|TEMP_DEFERRED|INELIGIBLE"
        json failed_reasons
        datetime created_at
    }

    DONATION {
        int id PK
        int donor_id FK
        int hospital_id FK
        datetime donated_at "90-day interval derived from these rows"
        int volume_ml
        int recorded_by_id FK "staff user, nullable"
    }

    BLOODBAG {
        int id PK
        int hospital_id FK
        string blood_group
        int volume_ml
        date collected_date
        date expiry_date "collected_date + 35 days"
        string status "AVAILABLE|RESERVED|ISSUED|EXPIRED|DISCARDED"
        int donation_id FK "nullable"
        int reserved_for_id FK "BloodRequest, nullable"
    }

    BLOODREQUEST {
        int id PK
        int patient_id FK "User"
        int hospital_id FK
        string blood_group
        int units_requested
        string urgency "ROUTINE|URGENT|EMERGENCY"
        string status "PENDING|ACCEPTED|REJECTED|FULFILLED"
        text rejection_reason "nullable"
        datetime created_at
    }

    ORGANDONATIONREQUEST {
        int id PK
        int donor_id FK
        int hospital_id FK
        string organ_type "KIDNEY|LIVER|HEART|LUNG|CORNEA|PANCREAS|SKIN"
        string status "PENDING|REQUESTED|APPROVED|REJECTED"
        datetime created_at
        datetime decided_at "nullable"
    }

    NOTIFICATION {
        int id PK
        int user_id FK
        string subject
        text body
        bool is_read
        datetime created_at
    }

    AUDITLOG {
        int id PK
        int actor_id FK "nullable, SET_NULL"
        string action
        string entity_type
        string entity_id
        json details
        datetime created_at
    }
```

## Design notes

**Nothing computed is stored.** Stock levels are counted from `BLOODBAG` rows
with `status = AVAILABLE`, grouped by hospital and blood group. A donor's next
eligible date is derived from their most recent `DONATION` row, and their age
from `date_of_birth`. No counter or cached date exists to drift out of step
with reality.

**`BLOODBAG.reserved_for`** ties a reserved bag to the request that reserved it,
so fulfilling one request can never consume another request's reservation. The
reservation and issue both run inside `transaction.atomic()` with
`select_for_update()`, re-checking status under the lock.

**`AUDITLOG` uses a loose reference** (`entity_type` + `entity_id`) rather than
foreign keys, so an audit entry survives the deletion of whatever it describes —
an audit trail that disappears with its subject is not an audit trail.

**Privacy boundaries** live in views and querysets, not in the schema: patients
never see donor identities, donors never see patient details, staff are scoped
to their own hospital through `STAFFPROFILE`, and hospitals flagged `is_hidden`
are filtered out for every non-admin. `DONOR.id_document` is reachable only
through an ADMIN-gated view — `MEDIA_ROOT` has no URL route at all.

**One donor, one user.** `DONOR` and `STAFFPROFILE` are both `OneToOne` on
`USER`, so a person's role determines which profile they can hold. Patients need
no profile row — they are simply a `USER` with `role = PATIENT`.
