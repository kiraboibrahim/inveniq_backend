import datetime
from decimal import Decimal

import pytest
from django.core import mail

from inventory.models import Branch, Product, Stock
from inventory.tasks import send_due_debt_reminders
from sales.models import Sale
from sales.serializers import SaleSerializer
from stakeholders.models import Customer


@pytest.fixture
def setup_data(db):
    branch = Branch.objects.create(name="Kampala Branch", code="KLA")
    product = Product.objects.create(
        sku="TEST-SKU", name="Test Product", price=Decimal("10000.00")
    )
    stock = Stock.objects.create(product=product, branch=branch, quantity=100)
    customer = Customer.objects.create(
        company_name="Acme Corp",
        contact_person="John Doe",
        email="john@example.com",
    )
    return {
        "branch": branch,
        "product": product,
        "stock": stock,
        "customer": customer,
    }


@pytest.mark.django_db
class TestSaleCreditAndDebt:
    def test_cash_sale_default_paid(self, setup_data):
        """Test that a cash sale is automatically marked as paid."""
        serializer = SaleSerializer(
            data={
                "branch": setup_data["branch"].id,
                "customer": setup_data["customer"].id,
                "total_amount": 50000.00,
                "payment_method": "cash",
                "items": [
                    {
                        "product": setup_data["product"].id,
                        "quantity": 5,
                        "unit_price": 10000.00,
                        "subtotal": 50000.00,
                    }
                ],
            }
        )
        assert serializer.is_valid(), serializer.errors
        sale = serializer.save()

        assert sale.payment_method == "cash"
        assert sale.is_paid is True
        assert sale.paid_amount == Decimal("50000.00")
        assert sale.due_date is None

        # Check customer stats: cash sale increments lifetime value
        setup_data["customer"].refresh_from_db()
        assert setup_data["customer"].lifetime_value == Decimal("50000.00")
        assert setup_data["customer"].outstanding_balance == Decimal("0.00")

    def test_credit_sale_requires_due_date(self, setup_data):
        """Test that a credit sale requires a due date."""
        serializer = SaleSerializer(
            data={
                "branch": setup_data["branch"].id,
                "customer": setup_data["customer"].id,
                "total_amount": 50000.00,
                "payment_method": "credit",
                "items": [
                    {
                        "product": setup_data["product"].id,
                        "quantity": 5,
                        "unit_price": 10000.00,
                        "subtotal": 50000.00,
                    }
                ],
            }
        )
        assert not serializer.is_valid()
        assert "due_date" in serializer.errors

    def test_credit_sale_initializes_unpaid(self, setup_data):
        """Test that a credit sale is initialized as unpaid.

        Also check that it sets the customer outstanding balance.
        """
        due_date = datetime.date.today() + datetime.timedelta(days=7)
        serializer = SaleSerializer(
            data={
                "branch": setup_data["branch"].id,
                "customer": setup_data["customer"].id,
                "total_amount": 50000.00,
                "payment_method": "credit",
                "due_date": due_date.isoformat(),
                "items": [
                    {
                        "product": setup_data["product"].id,
                        "quantity": 5,
                        "unit_price": 10000.00,
                        "subtotal": 50000.00,
                    }
                ],
            }
        )
        assert serializer.is_valid(), serializer.errors
        sale = serializer.save()

        assert sale.payment_method == "credit"
        assert sale.is_paid is False
        assert sale.paid_amount == Decimal("0.00")
        assert sale.due_date == due_date

        # Check customer stats: credit sale increments outstanding balance
        setup_data["customer"].refresh_from_db()
        assert setup_data["customer"].outstanding_balance == Decimal("50000.00")
        assert setup_data["customer"].lifetime_value == Decimal("0.00")

    def test_payment_allocation_fifo(self, setup_data):
        """Test that customer payment allocates to credit sales.

        Uses FIFO order to distribute payments.
        """
        customer = setup_data["customer"]
        branch = setup_data["branch"]

        # Let's create two credit sales manually
        due_date = datetime.date.today() + datetime.timedelta(days=7)

        # Sale 1: 30,000 UGX
        sale1 = Sale.objects.create(
            branch=branch,
            customer=customer,
            total_amount=Decimal("30000.00"),
            payment_method="credit",
            due_date=due_date,
            is_paid=False,
            paid_amount=Decimal("0.00"),
        )
        # Sale 2: 50,000 UGX
        sale2 = Sale.objects.create(
            branch=branch,
            customer=customer,
            total_amount=Decimal("50000.00"),
            payment_method="credit",
            due_date=due_date,
            is_paid=False,
            paid_amount=Decimal("0.00"),
        )

        customer.outstanding_balance = Decimal("80000.00")
        customer.save()

        # Let's record a payment of 45,000 UGX.
        # This should fully cover Sale 1 (30,000) and partially cover Sale 2 (15,000).
        from django.contrib.auth import get_user_model
        from rest_framework.test import APIRequestFactory, force_authenticate

        from stakeholders.views import CustomerViewSet

        User = get_user_model()
        user = User.objects.create_user(
            email="staff@example.com", password="password", role="staff"
        )

        factory = APIRequestFactory()
        request = factory.post(
            f"/api/stakeholders/customers/{customer.id}/record-payment/",
            {"amount": 45000.00, "note": "Partial repayment"},
            format="json",
        )
        force_authenticate(request, user=user)

        view = CustomerViewSet.as_view({"post": "record_payment"})
        response = view(request, pk=customer.id)
        assert response.status_code == 200

        # Verify Sale 1 is fully paid
        sale1.refresh_from_db()
        assert sale1.is_paid is True
        assert sale1.paid_amount == Decimal("30000.00")

        # Verify Sale 2 is partially paid
        sale2.refresh_from_db()
        assert sale2.is_paid is False
        assert sale2.paid_amount == Decimal("15000.00")

        # Verify customer outstanding balance is reduced
        customer.refresh_from_db()
        assert customer.outstanding_balance == Decimal("35000.00")
        assert customer.lifetime_value == Decimal("45000.00")

    def test_send_due_debt_reminders_task(self, setup_data):
        """Test that periodic task send_due_debt_reminders sends emails.

        Verifies alerts for overdue or due sales.
        """
        customer = setup_data["customer"]
        branch = setup_data["branch"]

        today = datetime.date.today()

        # Overdue sale: due 5 days ago
        sale_overdue = Sale.objects.create(
            branch=branch,
            customer=customer,
            total_amount=Decimal("40000.00"),
            payment_method="credit",
            due_date=today - datetime.timedelta(days=5),
            is_paid=False,
            paid_amount=Decimal("0.00"),
        )
        # Due today sale: due today
        sale_due_today = Sale.objects.create(
            branch=branch,
            customer=customer,
            total_amount=Decimal("20000.00"),
            payment_method="credit",
            due_date=today,
            is_paid=False,
            paid_amount=Decimal("0.00"),
        )
        # Not due yet sale: due in 5 days
        Sale.objects.create(
            branch=branch,
            customer=customer,
            total_amount=Decimal("60000.00"),
            payment_method="credit",
            due_date=today + datetime.timedelta(days=5),
            is_paid=False,
            paid_amount=Decimal("0.00"),
        )

        # Clear outbox
        mail.outbox = []

        # Run the task
        send_due_debt_reminders()

        # Assert only 2 emails were sent (overdue and due today)
        assert len(mail.outbox) == 2

        subjects = [email.subject for email in mail.outbox]
        assert (
            f"Payment Reminder: Invoice #{sale_overdue.id} - Kampala Branch" in subjects
        )
        assert (
            f"Payment Reminder: Invoice #{sale_due_today.id} - Kampala Branch"
            in subjects
        )

        # Verify email contents of one of the emails
        email = [
            e for e in mail.outbox if f"Invoice #{sale_due_today.id}" in e.subject
        ][0]
        assert customer.contact_person in email.body
        assert "UGX 20,000" in email.body
