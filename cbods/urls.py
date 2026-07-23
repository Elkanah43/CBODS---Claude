from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("donors/", include("donors.urls")),
    path("inventory/", include("inventory.urls")),
    path("requests/", include("requests_app.urls")),
    path("organs/", include("organs.urls")),
    path("notifications/", include("notifications.urls")),
    path("audit/", include("audit.urls")),
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
