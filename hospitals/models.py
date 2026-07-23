from django.conf import settings
from django.db import models


class HospitalQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Hidden hospitals are invisible to everyone except admins."""
        if user.is_authenticated and (user.is_superuser or user.role == "ADMIN"):
            return self
        return self.filter(is_hidden=False)


class Hospital(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    services_offered = models.TextField(blank=True)
    organ_requirements = models.TextField(blank=True)
    is_hidden = models.BooleanField(default=False)

    objects = HospitalQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class StaffProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_profile")
    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name="staff")

    def __str__(self):
        return f"{self.user.username} @ {self.hospital.name}"
