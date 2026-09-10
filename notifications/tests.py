"""Notification emails go to the address on the user's account — and nowhere else.

The service creates the in-app row and, when the account has an email address,
sends one email to exactly that address. These tests pin that down: the
recipient is always the address currently on the account, accounts without an
email get no email (but still their row), and there is no path that sends to
an unregistered address.
"""
from django.core import mail
from django.test import TestCase

from accounts.models import Role, User

from .models import Notification
from .services import notify, notify_many


class NotificationEmailRoutingTests(TestCase):
    def setUp(self):
        mail.outbox = []

    def test_notification_email_goes_to_the_account_address(self):
        user = User.objects.create_user(
            username="notify1", email="notify1@example.com", password="x",
            role=Role.PATIENT,
        )
        notify(user, "Bag expiring", "Bag B-1234 expires soon.")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [user.email])
        self.assertEqual(mail.outbox[0].subject, "Bag expiring")
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_account_without_an_email_gets_no_email_but_still_a_row(self):
        user = User.objects.create_user(username="notify2", email="", password="x")
        notify(user, "Subject", "Body")
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)

    def test_notification_follows_the_address_now_on_the_account(self):
        user = User.objects.create_user(
            username="notify3", email="old@example.com", password="x",
        )
        user.email = "current@example.com"
        user.save(update_fields=["email"])
        notify(user, "Subject", "Body")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["current@example.com"])
        self.assertNotIn("old@example.com", mail.outbox[0].to)

    def test_notify_many_sends_exactly_one_email_per_account_address(self):
        u1 = User.objects.create_user(username="notify4", email="a@example.com", password="x")
        u2 = User.objects.create_user(username="notify5", email="b@example.com", password="x")
        u3 = User.objects.create_user(username="notify6", email="", password="x")
        notify_many([u1, u2, u3], "Low stock", "Only 1 bag of O+ left.")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox), ["a@example.com", "b@example.com"]
        )
        self.assertEqual(Notification.objects.count(), 3)