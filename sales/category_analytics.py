from django.db.models import Sum
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.models import Category

from .models import SaleItem


class CategoryPerformanceView(APIView):
    def get(self, request):
        categories = Category.objects.all()
        data = []
        colors = [
            "var(--color-chart-1)",
            "var(--color-chart-2)",
            "var(--color-chart-3)",
            "var(--color-chart-4)",
            "var(--color-chart-5)",
        ]

        for i, cat in enumerate(categories):
            revenue = (
                SaleItem.objects.filter(product__category=cat).aggregate(
                    total=Sum("subtotal")
                )["total"]
                or 0
            )
            data.append(
                {
                    "category": cat.name,
                    "revenue": float(revenue),
                    "color": colors[i % len(colors)],
                }
            )

        # Sort by revenue descending
        data.sort(key=lambda x: x["revenue"], reverse=True)
        return Response(data)
