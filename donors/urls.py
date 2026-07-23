from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.donor_profile, name="donor_profile"),
    path("approvals/", views.approval_queue, name="donor_approval_queue"),
    path("approvals/<int:donor_id>/", views.approval_detail, name="donor_approval_detail"),
    path("search/", views.donor_search, name="donor_search"),
    path("screening/", views.screening_list, name="screening_list"),
    path("screening/<int:donor_id>/", views.screening_run, name="screening_run"),
]
