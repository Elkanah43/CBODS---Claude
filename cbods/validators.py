"""Shared validators for contact details (email, phone).

The same rules must hold everywhere a person types a phone number or email —
donor registration, hospital registration, staff provisioning, profile edits
and the Django admin. Applying them on the model fields (as with the
government-ID validators in donors/validators.py) keeps every form that
renders those fields in agreement, and redeclared form fields add them
explicitly where a ModelForm would otherwise drop them.

Phone numbers are Ghanaian mobiles, entered as the 9 digits that follow the
country code, and stored consistently in international form: ``+233XXXXXXXXX``.
The frontend enforces this for usability, but these validators are the real
gate — a hand-crafted HTTP request is checked here, never trusted to the
browser.
"""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

# Separators people use when writing a phone number, besides digits: the
# leading plus for international dialling, and grouping characters.
_PHONE_SEPARATORS = set(" ()+-.")


# ---------------------------------------------------------------------------
# Ghanaian mobile network prefixes — the ONE source of truth for the backend.
# The frontend receives the same table from the server (see the
# ghana_network_prefixes context processor) so the two sides cannot drift.
#
# NOTE ON MOBILE NUMBER PORTABILITY (MNP): Ghana allows subscribers to switch
# networks while keeping their number, so the prefix identifies the number's
# allocated/original network, NOT necessarily the subscriber's current one.
# The detected network is therefore used for registration, display, filtering
# and application logic only — never as proof of where a number is actually
# provisioned today.
# ---------------------------------------------------------------------------
GHANA_NETWORK_PREFIXES = {
    "MTN Ghana": ["24", "25", "53", "54", "55", "59"],
    "Telecel Ghana": ["20", "50"],
    "AirtelTigo Ghana": ["26", "27", "56", "57"],
}
GHANA_COUNTRY_CODE = "+233"
_PREFIX_TO_NETWORK = {
    prefix: network
    for network, prefixes in GHANA_NETWORK_PREFIXES.items()
    for prefix in prefixes
}


def detect_ghana_network(value):
    """The network a number was allocated to, or ``None`` when it is not a
    recognised Ghanaian mobile prefix. Tolerates any of the accepted input
    forms (9-digit national, ``+233``/``233`` international, light formatting).
    """
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if digits.startswith("233") and len(digits) == 12:
        digits = digits[3:]
    if len(digits) == 10 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9:
        return None
    return _PREFIX_TO_NETWORK.get(digits[:2])


def normalize_ghana_phone_number(value):
    """Validate and return the number as ``+233XXXXXXXXX`` (13 characters).

    Accepts the 9-digit national form (``241234567``), the international form
    (``+233241234567`` / ``233241234567``) — so a pasted or API-supplied full
    number is still safe — and light formatting (spaces, dashes, parentheses).
    The legacy 10-digit leading-zero form (``0241234567``) is rejected: the
    app's fields ask for the 9 digits after ``+233``, and accepting it would
    let a second spelling of the same number past the unique constraint.

    Raises :class:`django.core.exceptions.ValidationError` with a
    user-friendly message on any problem.
    """
    if value is None:
        value = ""
    value = str(value).strip()
    if value == "":
        raise ValidationError("Phone number is required.")
    if any(not (ch.isdigit() or ch in _PHONE_SEPARATORS) for ch in value):
        raise ValidationError("Please enter numbers only.")
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("233") and len(digits) == 12:
        national = digits[3:]
    else:
        national = digits
    if len(national) != 9:
        raise ValidationError(
            "Phone number must contain exactly 9 digits (e.g. 241234567)."
        )
    if national[:2] not in _PREFIX_TO_NETWORK:
        raise ValidationError("Invalid Ghana mobile network prefix.")
    return GHANA_COUNTRY_CODE + national


def validate_ghana_phone_number(value):
    """Model/field validator: valid numbers pass, everything else is rejected.

    Blank is allowed here so the model can represent "no phone yet" — the
    registration forms decide that a phone is required, and the admin may
    provision accounts without one. Normalisation to ``+233...`` happens in
    ``cbods.fields.GhanaPhoneField.to_python`` wherever the field is bound;
    this validator re-checks the result so no path can slip a bad value
    through.
    """
    if not value:
        return
    normalize_ghana_phone_number(value)


# Backward-compatible name: the 0003/0004/0005 migrations reference
# cbods.validators.validate_phone_number, so the old import must keep
# resolving even after the rename.
validate_phone_number = validate_ghana_phone_number


def validate_email_address(value):
    """A real email address, not a phone number typed into the wrong box.

    Django's own validator already rejects malformed addresses; this catches
    digit-only input (e.g. "0241234567") first with a message that points at
    the right field. Emails that merely contain digits (john2@gmail.com) are
    untouched.
    """
    if not value:
        return
    value = value.strip()
    if all(ch.isdigit() or ch in _PHONE_SEPARATORS for ch in value) and any(ch.isdigit() for ch in value):
        raise ValidationError("That looks like a phone number. Enter your email address here.")
    validate_email(value)