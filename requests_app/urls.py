from django.urls import path

from . import views

urlpatterns = [
    path("hospitals/", views.hospital_list, name="hospital_list"),
    path("new/<int:hospital_id>/", views.request_create, name="request_create"),
    path("mine/", views.my_requests, name="my_requests"),
    path("inbox/", views.request_inbox, name="request_inbox"),
    path("action/<int:request_id>/", views.request_action, name="request_action"),
    path("match/", views.compatibility_check, name="compatibility_check"),
    path("suggestions/<int:request_id>/", views.donor_suggestions, name="donor_suggestions"),
]
