from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.hospital_register, name="hospital_register"),
    path("profile/", views.hospital_profile, name="hospital_profile"),
    path("staff/", views.hospital_staff, name="hospital_staff"),
    path("staff/add/", views.hospital_staff_add, name="hospital_staff_add"),
    path("staff/<int:staff_id>/remove/", views.hospital_staff_remove, name="hospital_staff_remove"),
    path("approvals/", views.hospital_approval_queue, name="hospital_approval_queue"),
    path(
        "approvals/<int:hospital_id>/",
        views.hospital_approval_action,
        name="hospital_approval_action",
    ),
    path("manage/", views.hospital_admin_list, name="hospital_admin_list"),
    path(
        "manage/<int:hospital_id>/toggle-hidden/",
        views.hospital_admin_toggle_hidden,
        name="hospital_admin_toggle_hidden",
    ),
    path("reports/", views.hospital_reports, name="hospital_reports"),
    path("activity/", views.hospital_activity, name="hospital_activity"),
]
