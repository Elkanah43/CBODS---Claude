"""Per-rule password feedback for the registration form.

Thin wrapper over the AUTH_PASSWORD_VALIDATORS configured in settings, so the
live checklist on the register page is driven by the same validators that run
on submit. Adding or removing a validator in settings changes the checklist
with no template or JavaScript edit.
"""
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError


def _rule_id(validator):
    return validator.__class__.__name__


def _validators():
    # Cached by Django, so the 20k-entry common-password list is read from
    # disk once per process rather than once per keystroke.
    return password_validation.get_default_password_validators()


def get_rules():
    """The configured validators as [{"id", "text"}], in settings order."""
    return [{"id": _rule_id(v), "text": v.get_help_text()} for v in _validators()]


def check(password, user=None):
    """Map of rule id -> bool for `password`.

    A blank password reports every rule as unmet. Most validators accept the
    empty string trivially (only the length check rejects it), which would
    otherwise paint an untouched form with green ticks.
    """
    validators = _validators()
    if not password:
        return {_rule_id(v): False for v in validators}

    results = {}
    for validator in validators:
        try:
            validator.validate(password, user)
        except ValidationError:
            results[_rule_id(validator)] = False
        else:
            results[_rule_id(validator)] = True
    return results
