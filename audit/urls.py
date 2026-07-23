from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("log/", views.audit_log, name="audit_log"),
    path("export/<str:report>/", views.export_csv, name="export_csv"),
]
