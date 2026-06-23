import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from alerts.models import Alert

from .models import Stock

logger = logging.getLogger(__name__)


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
                description__icontains=product.name,
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
                description__icontains=product.name,
            ).update(is_resolved=True)
        else:
            # Resolve both Out of Stock and Low Stock Warning alerts when stock is replenished
            Alert.objects.filter(
                branch=branch,
                is_resolved=False,
                title__in=["Out of Stock", "Low Stock Warning"],
                description__icontains=product.name,
            ).update(is_resolved=True)
    except Exception as e:
        logger.error(
            f"Error checking/updating stock level alert for {product.name}: {e}"
        )
