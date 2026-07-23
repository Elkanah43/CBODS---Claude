"""In-app notification rows plus console email, one call."""
from django.core.mail import send_mail

from .models import Notification


def notify(user, subject, body):
    Notification.objects.create(user=user, subject=subject, body=body)
    if user.email:
        send_mail(subject, body, None, [user.email], fail_silently=True)


def notify_many(users, subject, body):
    for user in users:
        notify(user, subject, body)
