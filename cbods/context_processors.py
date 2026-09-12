"""Template context shared across the site.

``ghana_network_prefixes`` hands the backend's single source of truth for
Ghanaian mobile prefixes to the frontend, which renders it as JSON for
``ghana-phone.js``. The browser never keeps its own copy of the prefix table,
so the two sides cannot disagree.
"""
from .validators import GHANA_NETWORK_PREFIXES


def ghana_phone(request):
    return {"ghana_network_prefixes": GHANA_NETWORK_PREFIXES}