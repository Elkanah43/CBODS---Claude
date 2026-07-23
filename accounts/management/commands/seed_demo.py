"""Seed demo data: 3 hospitals (one hidden), ~25 donors across groups/cities/
statuses, bags in every state incl. near-expiry, sample blood and organ requests.

Re-runnable: wipes previously seeded demo rows (usernames prefixed demo_) first.
Passwords for every demo account: demo12345
"""
import datetime
import random
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Role, User
from donors.models import Donor, ScreeningRecord
from donors.services import screen_donor
from hospitals.models import Hospital, StaffProfile
from inventory.models import BagStatus, BloodBag, Donation
from organs.models import OrganDonationRequest
from requests_app.models import BloodRequest

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000d4944415478da63fcff9fa10e0002d40197ec1f83660000000049454e44ae426082"
)

GROUPS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
# Greater Accra cities plus Koforidua (Eastern Region, the closest neighbouring region)
CITIES = ["Accra", "Tema", "Madina", "Kasoa", "Koforidua"]
FIRST = ["Kwame", "Ama", "Kofi", "Akosua", "Yaw", "Abena", "Kwesi", "Efua",
         "Kojo", "Adwoa", "Nana", "Esi", "Kwabena", "Akua", "Fiifi", "Araba",
         "Kwaku", "Afia", "Yaa", "Kobina", "Adjoa", "Ekow", "Aba", "Kwadwo", "Afua"]
LAST = ["Mensah", "Owusu", "Boateng", "Asante", "Appiah", "Agyemang", "Addo",
        "Ofori", "Ankrah", "Tetteh", "Quartey", "Lartey", "Amankwah", "Darko",
        "Osei", "Gyasi", "Bediako", "Sarpong", "Frimpong", "Acheampong",
        "Adjei", "Baah", "Danso", "Nkrumah", "Yeboah"]


class Command(BaseCommand):
    help = "Seed demonstration data for CBODS."

    def handle(self, *args, **options):
        random.seed(42)
        self._wipe()
        hospitals = self._hospitals()
        staff = self._staff(hospitals)
        donors = self._donors()
        self._screen_and_donate(donors, hospitals, staff)
        self._bags(hospitals)
        patients = self._patients()
        self._blood_requests(patients, hospitals)
        self._organ_requests(donors, hospitals)
        self.stdout.write(self.style.SUCCESS(
            "Seeded: 3 hospitals (1 hidden), "
            f"{Donor.objects.filter(user__username__startswith='demo_').count()} donors, "
            f"{BloodBag.objects.count()} bags, "
            f"{BloodRequest.objects.count()} blood requests, "
            f"{OrganDonationRequest.objects.count()} organ requests. "
            "All demo passwords: demo12345"
        ))

    def _wipe(self):
        Hospital.objects.filter(name__startswith="Demo ").delete()
        User.objects.filter(username__startswith="demo_").delete()

    def _hospitals(self):
        h1 = Hospital.objects.create(
            name="Demo Accra Central Hospital", city="Accra",
            address="12 Independence Ave, Ridge, Accra",
            phone="030-222-1111", services_offered="Blood bank, transfusion, organ intake",
            organ_requirements="Kidney, liver, cornea",
        )
        h2 = Hospital.objects.create(
            name="Demo Tema Community Hospital", city="Tema",
            address="Community 4, Hospital Rd, Tema",
            phone="030-333-2222", services_offered="Blood bank, transfusion",
            organ_requirements="Cornea, skin",
        )
        h3 = Hospital.objects.create(
            name="Demo Koforidua Clinic", city="Koforidua",
            address="8 Galloway Rd, Koforidua, Eastern Region",
            phone="034-222-3333", services_offered="Suspended pending review", is_hidden=True,
        )
        return [h1, h2, h3]

    def _staff(self, hospitals):
        staff = []
        for i, hospital in enumerate(hospitals, start=1):
            user = User.objects.create_user(
                username=f"demo_staff{i}", password="demo12345",
                email=f"staff{i}@cbods.local", role=Role.HOSPITAL_STAFF,
            )
            StaffProfile.objects.create(user=user, hospital=hospital)
            staff.append(user)
        if not User.objects.filter(username="demo_admin").exists():
            User.objects.create_user(
                username="demo_admin", password="demo12345",
                email="admin@cbods.local", role=Role.ADMIN, is_staff=True,
            )
        return staff

    def _donors(self):
        donors = []
        today = timezone.localdate()
        for i, name in enumerate(FIRST):
            user = User.objects.create_user(
                username=f"demo_donor{i + 1}", password="demo12345",
                email=f"donor{i + 1}@cbods.local", role=Role.DONOR,
            )
            status = "APPROVED" if i < 18 else ("PENDING" if i < 22 else "REJECTED")
            # mainly Greater Accra (Accra, Tema, Madina, Kasoa); a few from Koforidua
            city = random.choices(CITIES, weights=[8, 5, 4, 4, 2])[0]
            donor = Donor(
                user=user,
                full_name=f"{name} {LAST[i]}",
                date_of_birth=today - datetime.timedelta(days=365 * random.randint(19, 55) + 100),
                sex=random.choice(["M", "F"]),
                blood_group=GROUPS[i % 8],
                weight_kg=Decimal(random.randint(52, 95)),
                city=city,
                contact_phone=f"024-{100 + i}-{4000 + i}",
                medical_history="None noted",
                registration_status=status,
                rejection_reason="ID document unreadable" if status == "REJECTED" else None,
            )
            donor.id_document.save(f"demo_id_{i + 1}.png", ContentFile(PNG), save=False)
            donor.save()
            donors.append(donor)
        return donors

    def _screen_and_donate(self, donors, hospitals, staff):
        now = timezone.now()
        approved = [d for d in donors if d.registration_status == "APPROVED"]
        for i, donor in enumerate(approved[:10]):
            record = screen_donor(donor, Decimal("13.5"), 120, 80)
            hospital = hospitals[i % 2]
            if record.outcome == "ELIGIBLE" and i < 6:
                donated_at = now - datetime.timedelta(days=random.choice([2, 10, 40, 95, 120, 200]))
                donation = Donation.objects.create(
                    donor=donor, hospital=hospital, donated_at=donated_at,
                    volume_ml=450, recorded_by=staff[i % 2],
                )
                collected = donated_at.date()
                BloodBag.objects.create(
                    hospital=hospital, blood_group=donor.blood_group, volume_ml=450,
                    collected_date=collected,
                    expiry_date=collected + datetime.timedelta(days=35),
                    status=BagStatus.AVAILABLE if collected + datetime.timedelta(days=35) >= timezone.localdate() else BagStatus.EXPIRED,
                    donation=donation,
                )
        # one deferred screening for variety
        if len(approved) > 10:
            screen_donor(approved[10], Decimal("11.0"), 120, 80)

    def _bags(self, hospitals):
        """Extra bags so every state and near-expiry appear at visible hospitals."""
        today = timezone.localdate()
        h1, h2, _ = hospitals
        spec = [
            (h1, "O+", BagStatus.AVAILABLE, 20), (h1, "O+", BagStatus.AVAILABLE, 12),
            (h1, "O+", BagStatus.AVAILABLE, 4),  # near-expiry
            (h1, "A+", BagStatus.AVAILABLE, 25), (h1, "A+", BagStatus.AVAILABLE, 3),
            (h1, "B+", BagStatus.AVAILABLE, 15),
            (h1, "O-", BagStatus.AVAILABLE, 18), (h1, "O-", BagStatus.AVAILABLE, 6),
            (h1, "AB+", BagStatus.RESERVED, 10),
            (h1, "B-", BagStatus.ISSUED, 9),
            (h1, "A-", BagStatus.DISCARDED, 14),
            (h2, "O+", BagStatus.AVAILABLE, 22), (h2, "B+", BagStatus.AVAILABLE, 5),
            (h2, "AB-", BagStatus.AVAILABLE, 30), (h2, "A+", BagStatus.AVAILABLE, 2),
        ]
        for hospital, group, status, days_left in spec:
            BloodBag.objects.create(
                hospital=hospital, blood_group=group, volume_ml=450,
                collected_date=today - datetime.timedelta(days=35 - days_left),
                expiry_date=today + datetime.timedelta(days=days_left),
                status=status,
            )
        # one already-expired bag awaiting the expire_bags command
        BloodBag.objects.create(
            hospital=h1, blood_group="AB-", volume_ml=450,
            collected_date=today - datetime.timedelta(days=40),
            expiry_date=today - datetime.timedelta(days=5),
            status=BagStatus.AVAILABLE,
        )

    def _patients(self):
        patients = []
        for i in range(1, 4):
            patients.append(
                User.objects.create_user(
                    username=f"demo_patient{i}", password="demo12345",
                    email=f"patient{i}@cbods.local", role=Role.PATIENT,
                )
            )
        return patients

    def _blood_requests(self, patients, hospitals):
        h1, h2, _ = hospitals
        BloodRequest.objects.create(patient=patients[0], hospital=h1, blood_group="O+", units_requested=2, urgency="ROUTINE")
        BloodRequest.objects.create(patient=patients[1], hospital=h1, blood_group="A+", units_requested=1, urgency="URGENT")
        BloodRequest.objects.create(patient=patients[2], hospital=h2, blood_group="AB-", units_requested=1, urgency="EMERGENCY")

    def _organ_requests(self, donors, hospitals):
        approved = [d for d in donors if d.registration_status == "APPROVED"]
        h1, h2, _ = hospitals
        OrganDonationRequest.objects.create(donor=approved[0], hospital=h1, organ_type="KIDNEY")
        OrganDonationRequest.objects.create(donor=approved[1], hospital=h1, organ_type="CORNEA", status="REQUESTED")
        OrganDonationRequest.objects.create(
            donor=approved[2], hospital=h2, organ_type="LIVER",
            status="APPROVED", decided_at=timezone.now(),
        )
