from django.urls import path

from . import views

urlpatterns = [
    path("new/", views.organ_request_create, name="organ_request_create"),
    path("mine/", views.organ_my_requests, name="organ_my_requests"),
    path("review/", views.organ_review_list, name="organ_review_list"),
    path("review/<int:request_id>/", views.organ_review_action, name="organ_review_action"),
]
