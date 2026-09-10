from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.donor_profile, name="donor_profile"),
    path("profile/edit/", views.donor_profile_edit, name="donor_profile_edit"),
    path("sites/", views.donation_sites, name="donation_sites"),
    path("sites/<int:hospital_id>/book/", views.book_appointment, name="book_appointment"),
    path("appointments/", views.my_appointments, name="my_appointments"),
    path("appointments/<int:appointment_id>/cancel/", views.appointment_cancel, name="appointment_cancel"),
    path("appointments/inbox/", views.appointment_inbox, name="appointment_inbox"),
    path("appointments/inbox/<int:appointment_id>/decide/", views.appointment_decide, name="appointment_decide"),
    path("approvals/", views.approval_queue, name="donor_approval_queue"),
    path("approvals/<int:donor_id>/", views.approval_detail, name="donor_approval_detail"),
    path("approvals/<int:donor_id>/id-document/", views.id_document, name="donor_id_document"),
    path("search/", views.donor_search, name="donor_search"),
    path("screening/", views.screening_list, name="screening_list"),
    path("screening/<int:donor_id>/", views.screening_run, name="screening_run"),
]
