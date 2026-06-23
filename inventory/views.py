from datetime import datetime

from django.db import transaction
from django.http import HttpResponse
from django.template.loader import render_to_string
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from accounts.permissions import IsManager, IsManagerOrReadOnly

from .models import Branch, Category, Product, PurchaseOrder, Stock, StockEntry
from .serializers import (
    BranchSerializer,
    CategorySerializer,
    ProductSerializer,
    PurchaseOrderSerializer,
    StockEntrySerializer,
    StockSerializer,
)


class BranchViewSet(viewsets.ModelViewSet):
    queryset = Branch.objects.all()
    serializer_class = BranchSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class ProductViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManagerOrReadOnly]
    serializer_class = ProductSerializer
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["category", "sku"]
    search_fields = ["name", "sku", "description"]
    ordering_fields = ["name", "price", "created_at"]
    pagination_class = None

    def get_queryset(self):
        return Product.objects.all().prefetch_related("stocks")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["branch"] = self.request.query_params.get("branch")
        return context

    @action(detail=False, methods=["post"], parser_classes=[MultiPartParser])
    def import_excel(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .tasks import process_excel_import

            file_bytes = file.read()
            branch_id = request.data.get("branch_id")
            process_excel_import.call_local(file_bytes, branch_id)
            return Response(
                {"message": "Excel import completed successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def download_template(self, request):
        import openpyxl
        from django.http import HttpResponse

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Template"

        # Headers
        headers = [
            "sku",
            "name",
            "category",
            "price",
            "quantity",
            "threshold",
            "description",
        ]
        ws.append(headers)

        # Example rows
        examples = [
            [
                "SKU-001",
                "Example Product 1",
                "Beverages",
                12.50,
                100,
                10,
                "This is an example product description",
            ],
            [
                "SKU-002",
                "Example Product 2",
                "Stationery",
                4.99,
                50,
                5,
                "Another example product",
            ],
        ]
        for row in examples:
            ws.append(row)

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = (
            "attachment; filename=product_import_template.xlsx"
        )
        wb.save(response)
        return response


class StockViewSet(viewsets.ModelViewSet):
    queryset = Stock.objects.all()
    serializer_class = StockSerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["product", "branch"]
    pagination_class = None


class StockEntryViewSet(viewsets.ModelViewSet):
    """Create and list stock entry records. Creating a StockEntry will also
    update (or create) the corresponding Stock aggregate row.
    """

    queryset = StockEntry.objects.all().order_by("-created_at")
    serializer_class = StockEntrySerializer
    permission_classes = [IsManagerOrReadOnly]
    filterset_fields = ["product", "branch"]
    pagination_class = None

    def perform_create(self, serializer):
        entry = serializer.save()
        stock, created = Stock.objects.get_or_create(
            product=entry.product,
            branch=entry.branch,
            defaults={"quantity": entry.quantity},
        )
        if not created:
            stock.quantity = stock.quantity + entry.quantity
            stock.save()


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """Create, retrieve, update and list purchase orders.

    Supports filtering by ``supplier``, ``branch``, and ``status``.

    Extra actions
    -------------
    GET  /purchase-orders/export-pdf/?supplier=<id>
        Returns a PDF document listing all purchase orders for the given supplier.
    """

    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsManagerOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["supplier", "branch", "status"]
    ordering_fields = ["created_at", "status"]
    pagination_class = None

    def get_queryset(self):
        return (
            PurchaseOrder.objects.prefetch_related("items__product")
            .select_related("supplier", "branch")
            .order_by("-created_at")
        )

    @action(
        detail=True,
        methods=["post"],
        url_path="update-status",
        permission_classes=[IsManager],
    )
    def update_status(self, request, pk=None):
        po = self.get_object()
        new_status = request.data.get("status")
        if new_status not in ["draft", "sent", "received"]:
            return Response(
                {"error": f"Invalid status: {new_status}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if po.status == "received":
            return Response(
                {"error": "Cannot change status of an already received order."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            po.status = new_status
            po.save()

            if new_status == "received":
                for item in po.items.all():
                    # Update stock and log entry
                    stock, created = Stock.objects.get_or_create(
                        product=item.product,
                        branch=po.branch,
                        defaults={"quantity": item.quantity},
                    )
                    if not created:
                        stock.quantity = stock.quantity + item.quantity
                        stock.save()

                    StockEntry.objects.create(
                        product=item.product,
                        branch=po.branch,
                        quantity=item.quantity,
                        note=f"Received from PO #{po.id}",
                    )

        return Response(PurchaseOrderSerializer(po).data)

    # ── PDF export ────────────────────────────────────────────────────────────

    @action(
        detail=False,
        methods=["get"],
        url_path="export-pdf",
        permission_classes=[IsManager],
    )
    def export_pdf(self, request):
        """
        GET /api/inventory/purchase-orders/export-pdf/?supplier=<id>

        Generates and streams a PDF order-history report for the requested supplier.
        """
        supplier_id = request.query_params.get("supplier")
        if not supplier_id:
            return Response(
                {"error": "Query parameter 'supplier' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from stakeholders.models import Supplier

            supplier = Supplier.objects.get(pk=supplier_id)
        except Supplier.DoesNotExist:
            return Response(
                {"error": "Supplier not found."}, status=status.HTTP_404_NOT_FOUND
            )

        orders = (
            PurchaseOrder.objects.filter(supplier=supplier)
            .prefetch_related("items__product")
            .select_related("branch")
            .order_by("-created_at")
        )

        # Annotate each order with a computed total so the template can render it
        for order in orders:
            order.order_total = sum(
                item.quantity * item.unit_cost for item in order.items.all()
            )

        grand_total = sum(getattr(o, "order_total", 0) for o in orders)
        received_count = orders.filter(status="received").count()
        pending_count = orders.filter(status__in=["draft", "sent"]).count()

        context = {
            "supplier": supplier,
            "orders": orders,
            "grand_total": grand_total,
            "total_orders": orders.count(),
            "received_count": received_count,
            "pending_count": pending_count,
            "generated_at": datetime.now().strftime("%d %b %Y, %H:%M"),
        }

        html_string = render_to_string("inventory/supplier_order_history.html", context)

        try:
            from weasyprint import HTML

            pdf_bytes = HTML(
                string=html_string, base_url=request.build_absolute_uri("/")
            ).write_pdf()
        except Exception as exc:
            return Response(
                {"error": f"PDF generation failed: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        supplier_slug = supplier.name.replace(" ", "-").lower()
        filename = f"order-history-{supplier_slug}.pdf"

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Access-Control-Expose-Headers"] = "Content-Disposition"
        return response
