"""Project-wide date/time display formats.

Unqualified ISO dates read the same to every reader, which matters on pages
that mix collection dates, expiry dates and audit timestamps. Anything not
listed here falls through to Django's own `en` formats.
"""

DATE_FORMAT = "Y-m-d"
DATETIME_FORMAT = "Y-m-d H:i"
SHORT_DATE_FORMAT = "Y-m-d"
SHORT_DATETIME_FORMAT = "Y-m-d H:i"
