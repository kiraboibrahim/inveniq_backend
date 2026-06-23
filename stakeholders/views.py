from decimal import Decimal

from django.db import transaction
from django.db.models import F
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsManager, IsStaff

from .models import Customer, Payment, Supplier
from .serializers import (
    CustomerSerializer,
    PaymentSerializer,
    RecordPaymentSerializer,
    SupplierSerializer,
)


class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsManager]
    pagination_class = None


class CustomerViewSet(viewsets.ModelViewSet):
    """Full CRUD for customers plus two extra actions:

    POST  /customers/{id}/record_payment/
        Record a debt repayment. Atomically decrements outstanding_balance and
        increments lifetime_value. Creates a Payment audit record.

    GET   /customers/{id}/payments/
        List all payment records for a customer (most-recent first).
    """

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsStaff]
    pagination_class = None

    # ── record_payment ────────────────────────────────────────────────────────

    @action(
        detail=True,
        methods=["post"],
        url_path="record-payment",
        permission_classes=[IsStaff],
    )
    def record_payment(self, request, pk=None):
        """
        POST /api/stakeholders/customers/{id}/record-payment/
        Body: { "amount": 50000, "note": "Cash received" }
        """
        customer = self.get_object()

        serializer = RecordPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        amount = Decimal(str(serializer.validated_data["amount"]))
        note = serializer.validated_data.get("note", "")

        if amount <= Decimal("0"):
            return Response(
                {"error": "Payment amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if amount > customer.outstanding_balance:
            return Response(
                {
                    "error": (
                        f"Payment of {amount} exceeds outstanding balance "
                        f"of {customer.outstanding_balance}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # Use F() expressions to avoid race conditions
            Customer.objects.filter(pk=customer.pk).update(
                outstanding_balance=F("outstanding_balance") - amount,
                lifetime_value=F("lifetime_value") + amount,
            )

            Payment.objects.create(
                customer=customer,
                amount=amount,
                note=note,
                recorded_by=request.user if request.user.is_authenticated else None,
            )

        customer.refresh_from_db()
        return Response(
            {
                "detail": "Payment recorded successfully.",
                "customer": CustomerSerializer(customer).data,
            },
            status=status.HTTP_200_OK,
        )

    # ── payments (history) ────────────────────────────────────────────────────

    @action(
        detail=True, methods=["get"], url_path="payments", permission_classes=[IsStaff]
    )
    def payments(self, request, pk=None):
        """
        GET /api/stakeholders/customers/{id}/payments/
        Returns the payment history for the customer.
        """
        customer = self.get_object()
        qs = Payment.objects.filter(customer=customer).select_related("recorded_by")
        return Response(PaymentSerializer(qs, many=True).data)
