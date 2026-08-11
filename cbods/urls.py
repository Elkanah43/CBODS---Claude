from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("donors/", include("donors.urls")),
    path("inventory/", include("inventory.urls")),
    path("requests/", include("requests_app.urls")),
    path("hospitals/", include("hospitals.urls")),
    path("organs/", include("organs.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]

# MEDIA_ROOT is deliberately NOT served here. The only uploads are donor
# government-ID scans, which are served solely by the admin-only
# donors.views.id_document view so they can never be fetched by URL alone.
