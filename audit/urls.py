from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("log/", views.audit_log, name="audit_log"),
]
