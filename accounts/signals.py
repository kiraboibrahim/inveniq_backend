"""
Signal handlers for accounts app.
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def user_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for User post_save.
    Add custom logic here (e.g., create user profile, send welcome email, etc.)
    """
    if created:
        # User was just created
        pass
