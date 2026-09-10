"""In-app notification rows plus email, one call.

Email uses the configured backend: the console backend by default (prints to
the server log), real SMTP when EMAIL_HOST is set.
"""
from django.core.mail import send_mail

from .models import Notification


def notify(user, subject, body):
    Notification.objects.create(user=user, subject=subject, body=body)
    if user.email:
        send_mail(subject, body, None, [user.email], fail_silently=True)


def notify_many(users, subject, body):
    for user in users:
        notify(user, subject, body)
