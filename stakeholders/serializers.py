from decimal import Decimal

from rest_framework import serializers

from .models import Customer, Payment, Supplier


class SupplierSerializer(serializers.ModelSerializer):
    contactPerson = serializers.CharField(source="contact_person")
    fulfillmentRating = serializers.IntegerField(source="fulfillment_rating")

    class Meta:
        model = Supplier
        fields = [
            "id",
            "name",
            "contactPerson",
            "email",
            "phone",
            "fulfillmentRating",
            "status",
            "created_at",
            "updated_at",
        ]


class CustomerSerializer(serializers.ModelSerializer):
    companyName = serializers.CharField(source="company_name")
    contactPerson = serializers.CharField(source="contact_person")
    lifetimeValue = serializers.DecimalField(
        source="lifetime_value",
        max_digits=15,
        decimal_places=2,
        required=False,
        default=0,
    )
    outstandingBalance = serializers.DecimalField(
        source="outstanding_balance",
        max_digits=15,
        decimal_places=2,
        required=False,
        default=0,
    )
    lastOrderDate = serializers.DateField(
        source="last_order_date", required=False, allow_null=True, default=None
    )

    class Meta:
        model = Customer
        fields = [
            "id",
            "companyName",
            "contactPerson",
            "email",
            "lifetimeValue",
            "outstandingBalance",
            "lastOrderDate",
            "created_at",
            "updated_at",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    """Read-only serializer used for listing a customer's payment history."""

    recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "amount", "note", "recorded_by_name", "created_at"]
        read_only_fields = fields

    def get_recorded_by_name(self, obj):
        if obj.recorded_by:
            return obj.recorded_by.get_full_name() or obj.recorded_by.email
        return None


class RecordPaymentSerializer(serializers.Serializer):
    """Input serializer for the record_payment action."""

    amount = serializers.DecimalField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.01")
    )
    note = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
