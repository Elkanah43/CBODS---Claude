from django.contrib import admin

from .models import Donor


@admin.register(Donor)
class DonorAdmin(admin.ModelAdmin):
    list_display = ["full_name", "blood_group", "city", "registration_status", "is_available"]
    list_filter = ["registration_status", "blood_group", "city", "is_available"]
    search_fields = ["full_name", "city"]
