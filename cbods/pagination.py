"""Shared list pagination so long tables stay fast as the data grows."""
from django.conf import settings
from django.core.paginator import Paginator


def paginate(request, queryset, per_page=None):
    """Return the Page for ?page=N. Out-of-range or non-numeric pages fall back
    to the first/last valid page instead of raising."""
    paginator = Paginator(queryset, per_page or settings.LIST_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))
