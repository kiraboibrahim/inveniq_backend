from django.db import models
from django.utils.translation import gettext_lazy as _


class Branch(models.Model):
    name = models.CharField(_("branch name"), max_length=100)
    code = models.CharField(_("branch code"), max_length=20, blank=True)
    location = models.CharField(_("location"), max_length=255, blank=True)
    manager = models.CharField(_("manager"), max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("branch")
        verbose_name_plural = _("branches")

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(_("category name"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("category")
        verbose_name_plural = _("categories")

    def __str__(self):
        return self.name


class Product(models.Model):
    sku = models.CharField(_("SKU/Barcode"), max_length=50, unique=True)
    name = models.CharField(_("product name"), max_length=255)
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name="products"
    )
    description = models.TextField(_("description"), blank=True)
    price = models.DecimalField(_("price"), max_digits=12, decimal_places=2)
    cost_price = models.DecimalField(
        _("cost price"), max_digits=12, decimal_places=2, default=0.00
    )
    primary_supplier = models.ForeignKey(
        "stakeholders.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    threshold = models.IntegerField(_("low stock threshold"), default=10)
    expiry_date = models.DateField(_("expiry date"), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Stock(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stocks"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="stocks")
    quantity = models.IntegerField(_("quantity on hand"), default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("stock")
        verbose_name_plural = _("stocks")
        unique_together = ("product", "branch")

    def __str__(self):
        return f"{self.product.name} at {self.branch.name}: {self.quantity}"


class StockEntry(models.Model):
    """A record of a stock addition or adjustment for a product at a branch.

    This is used to record stock receipts or manual adjustments as separate
    entries while the `Stock` model holds the current on-hand quantity.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="entries"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="entries")
    quantity = models.IntegerField(
        "quantity change", help_text="Positive to add, negative to remove"
    )
    note = models.CharField("note", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("stock entry")
        verbose_name_plural = _("stock entries")

    def __str__(self):
        return f"{self.quantity} of {self.product.sku} @ {self.branch.name} ({self.created_at.isoformat()})"


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("received", "Received"),
    ]

    supplier = models.ForeignKey(
        "stakeholders.Supplier",
        on_delete=models.CASCADE,
        related_name="purchase_orders",
    )
    branch = models.ForeignKey(
        Branch, on_delete=models.CASCADE, related_name="purchase_orders"
    )
    status = models.CharField(
        _("status"), max_length=20, choices=STATUS_CHOICES, default="draft"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("purchase order")
        verbose_name_plural = _("purchase orders")
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO #{self.id} - {self.supplier.name} ({self.status})"


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="purchase_order_items"
    )
    quantity = models.IntegerField(_("quantity"))
    unit_cost = models.DecimalField(_("unit cost"), max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = _("purchase order item")
        verbose_name_plural = _("purchase order items")

    def __str__(self):
        return f"{self.product.name} x {self.quantity} on PO #{self.purchase_order.id}"
