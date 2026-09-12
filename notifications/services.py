"""In-app notification rows plus email, one call.

Email uses the configured backend: the console backend by default (prints to
the server log), real SMTP when EMAIL_HOST is set.
"""
import logging

from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger("cbods.email")


def notify(user, subject, body):
    Notification.objects.create(user=user, subject=subject, body=body)
    if not user.email:
        return
    try:
        send_mail(subject, body, None, [user.email])
    except Exception as e:
        # A failed notification email must never break the workflow that
        # produced it (approving a donor, fulfilling a request, ...), which is
        # what fail_silently bought before. But silent swallowing made "no
        # email arrived" undiagnosable: a wrong/expired SMTP key or a server
        # started without EMAIL_HOST looked identical to delivery. Send with
        # errors enabled and catch here, so the log carries the reason while
        # the caller still sees success.
        logger.exception(
            "Failed to send notification email to %s for %r: %s",
            user.email,
            subject,
            e,
        )


def notify_many(users, subject, body):
    for user in users:
        notify(user, subject, body)
