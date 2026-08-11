from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from .models import HospitalApprovalStatus
from .utils import staff_hospital


def require_approved_hospital(view):
    """Gate a hospital feature on an APPROVED hospital.

    Admins bypass the hospital check entirely (they may view any hospital's
    data). Everyone else must be linked to a hospital whose registration has
    been approved; a pending or rejected registration is redirected to the
    dashboard, where the status banner explains what to do next.
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.is_superuser or request.user.role == "ADMIN":
            return view(request, *args, **kwargs)
        hospital = staff_hospital(request.user)
        if hospital is None:
            messages.error(request, "Your account is not linked to a hospital.")
            return redirect("dashboard")
        if hospital.approval_status != HospitalApprovalStatus.APPROVED:
            messages.error(
                request,
                "Your hospital registration is not yet approved. "
                "You will get full access once an administrator reviews it.",
            )
            return redirect("dashboard")
        return view(request, *args, **kwargs)

    return wrapped
