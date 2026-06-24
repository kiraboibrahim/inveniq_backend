from django.db import models
from django.utils.translation import gettext_lazy as _

from inventory.models import Branch, Product


class Sale(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="sales")
    customer = models.ForeignKey(
        "stakeholders.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )
    total_amount = models.DecimalField(
        _("total amount"), max_digits=15, decimal_places=2, default=0
    )
    payment_method = models.CharField(
        _("payment method"),
        max_length=20,
        default="cash",
        choices=[("cash", "Cash"), ("credit", "Credit")],
    )
    due_date = models.DateField(_("due date"), null=True, blank=True)
    paid_amount = models.DecimalField(
        _("paid amount"), max_digits=15, decimal_places=2, default=0
    )
    is_paid = models.BooleanField(_("is paid"), default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]

    def __str__(self):
        return f"Sale {self.id} at {self.branch.name} - {self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(_("quantity"))
    unit_price = models.DecimalField(_("unit price"), max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(_("subtotal"), max_digits=15, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
