from django.urls import path

from . import views

urlpatterns = [
    path("stock/", views.stock_dashboard, name="stock_dashboard"),
    path("donate/", views.record_donation, name="record_donation"),
]
