from django.db import models
from django.utils.translation import gettext_lazy as _


class Supplier(models.Model):
    name = models.CharField(_("company name"), max_length=255)
    contact_person = models.CharField(_("contact person"), max_length=100)
    email = models.EmailField(_("email"), unique=True)
    phone = models.CharField(_("phone"), max_length=20)
    fulfillment_rating = models.IntegerField(_("fulfillment rating"), default=0)
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=[("active", "Active"), ("inactive", "Inactive")],
        default="active",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    company_name = models.CharField(_("company name"), max_length=255)
    contact_person = models.CharField(_("contact person"), max_length=100)
    email = models.EmailField(_("email"), unique=True)
    lifetime_value = models.DecimalField(
        _("lifetime value"), max_digits=15, decimal_places=2, default=0
    )
    outstanding_balance = models.DecimalField(
        _("outstanding balance"), max_digits=15, decimal_places=2, default=0
    )
    last_order_date = models.DateField(_("last order date"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.company_name


class Payment(models.Model):
    """Records each debt repayment made by a customer."""

    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="payments"
    )
    amount = models.DecimalField(_("amount paid"), max_digits=15, decimal_places=2)
    note = models.CharField(_("note"), max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("payment")
        verbose_name_plural = _("payments")

    def __str__(self):
        return f"Payment of {self.amount} by {self.customer.company_name} on {self.created_at:%Y-%m-%d}"
