"""Shared form helpers for the Ghanaian phone fields.

The frontend renders every Ghanaian phone input as ``+233 | [9 digits]``:
a fixed, non-editable prefix beside a box that accepts exactly 9 digits.
These attributes make the input announce that contract to the browser, and
``data-ghana-phone`` is the hook the shared ``ghana-phone.js`` wires up.
"""
from django import forms

# Applied to every phone widget, whatever form it belongs to.
GHANA_PHONE_ATTRS = {
    "data-ghana-phone": "1",
    "inputmode": "numeric",
    "maxlength": "9",
    "pattern": "[0-9]{9}",
    "autocomplete": "tel",
    "placeholder": "241234567",
}


def ghana_phone_input(**extra):
    """A TextInput pre-configured for the 9-digit Ghanaian phone entry.

    Used when a form declares its phone field with an explicit widget (the
    signup forms redeclare the fields); ModelForms use
    :func:`apply_ghana_phone_attrs` instead.
    """
    attrs = dict(GHANA_PHONE_ATTRS)
    attrs.update(extra)
    return forms.TextInput(attrs=attrs)


def apply_ghana_phone_attrs(form, *field_names):
    """Stamp the phone attributes onto the named fields of a form, if present.

    Call from a form's ``__init__`` so ModelForms get the same frontend
    behaviour as the redeclared signup fields without touching Meta.
    """
    for name in field_names:
        if name in form.fields:
            form.fields[name].widget.attrs.update(GHANA_PHONE_ATTRS)