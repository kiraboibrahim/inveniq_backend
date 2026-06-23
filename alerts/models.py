from django.db import models
from django.utils.translation import gettext_lazy as _

from inventory.models import Branch


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ("critical", "Critical"),
        ("warning", "Warning"),
        ("info", "Info"),
    ]

    title = models.CharField(_("title"), max_length=255)
    description = models.TextField(_("description"))
    severity = models.CharField(_("severity"), max_length=10, choices=SEVERITY_CHOICES)
    is_resolved = models.BooleanField(_("is resolved"), default=False)
    # optional branch/shop context; null for legacy/global alerts
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="alerts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.severity})"
