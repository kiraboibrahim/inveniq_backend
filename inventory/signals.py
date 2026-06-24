import logging

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from alerts.models import Alert

from .models import PurchaseOrder, Stock

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=PurchaseOrder)
def track_po_status_before_save(sender, instance, **kwargs):
    if instance.id:
        try:
            instance._was_received = (
                PurchaseOrder.objects.get(pk=instance.id).status == "received"
            )
        except PurchaseOrder.DoesNotExist:
            instance._was_received = False
    else:
        instance._was_received = False


@receiver(post_save, sender=PurchaseOrder)
def handle_po_received_signal(sender, instance, created, **kwargs):
    from .tasks import send_supplier_po_received_email

    if instance.status == "received":
        was_received = getattr(instance, "_was_received", False)
        if not was_received and instance.supplier.email:
            send_supplier_po_received_email.delay(instance.id)


@receiver(post_save, sender=Stock)
def handle_stock_alert_check(sender, instance, **kwargs):
    # Local imports to prevent circular dependencies
    from .tasks import create_alert_and_notify

    product = instance.product
    branch = instance.branch
    qty = instance.quantity
    threshold = product.threshold

    try:
        if qty <= 0:
            # Create/Get Out of Stock alert
            create_alert_and_notify(
                title="Out of Stock",
                description=f"{product.name} is out of stock at {branch.name}.",
                branch=branch,
                severity="critical",
            )
            # Resolve any existing Low Stock Warning alerts for this product
            Alert.objects.filter(
                branch=branch,
                is_resolved=False,
                title="Low Stock Warning",
                description__startswith=f"{product.name} at {branch.name} is low:",
            ).update(is_resolved=True)
        elif qty <= threshold:
            # Create/Get Low Stock Warning alert
            create_alert_and_notify(
                title="Low Stock Warning",
                description=f"{product.name} at {branch.name} is low: {qty} remaining.",
                branch=branch,
                severity="warning",
            )
            # Resolve any Out of Stock alerts
            Alert.objects.filter(
                branch=branch,
                is_resolved=False,
                title="Out of Stock",
                description=f"{product.name} is out of stock at {branch.name}.",
            ).update(is_resolved=True)
        else:
            # Resolve both Out of Stock and Low Stock Warning alerts
            # when stock is replenished.
            Alert.objects.filter(
                branch=branch,
                is_resolved=False,
                title="Out of Stock",
                description=f"{product.name} is out of stock at {branch.name}.",
            ).update(is_resolved=True)

            Alert.objects.filter(
                branch=branch,
                is_resolved=False,
                title="Low Stock Warning",
                description__startswith=f"{product.name} at {branch.name} is low:",
            ).update(is_resolved=True)
    except Exception as e:
        logger.error(
            f"Error checking/updating stock level alert for {product.name}: {e}"
        )
