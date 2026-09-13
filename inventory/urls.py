from django.urls import path

from . import views

urlpatterns = [
    path("stock/", views.stock_dashboard, name="stock_dashboard"),
    path("donate/", views.record_donation, name="record_donation"),
    path("tti/", views.tti_screening_list, name="tti_screening_list"),
    path("tti/<int:donation_id>/", views.tti_screening_run, name="tti_screening_run"),
]
