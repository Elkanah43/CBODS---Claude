from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


@login_required
def notification_list(request):
    if request.method == "POST":
        request.user.notifications.filter(is_read=False).update(is_read=True)
        return redirect("notification_list")
    return render(
        request,
        "notifications/list.html",
        {"items": request.user.notifications.all()[:100]},
    )
