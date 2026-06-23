from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDay
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from inventory.models import Category

from .models import Sale, SaleItem


class SalesAnalyticsView(APIView):
    def get(self, request):
        # Last 7 days sales
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)

        sales = (
            Sale.objects.filter(timestamp__range=[start_date, end_date])
            .annotate(date=TruncDay("timestamp"))
            .values("date")
            .annotate(revenue=Sum("total_amount"))
            .order_by("date")
        )

        categories = Category.objects.all()
        data = []
        for s in sales:
            point = {
                "date": s["date"].strftime("%a"),
                "revenue": float(s["revenue"]),
            }
            # Add dynamic category revenue
            for cat in categories:
                cat_revenue = (
                    SaleItem.objects.filter(
                        sale__timestamp__date=s["date"].date(), product__category=cat
                    ).aggregate(total=Sum("subtotal"))["total"]
                    or 0
                )
                point[cat.name] = float(cat_revenue)
            data.append(point)

        return Response(data)


class TopProductsView(APIView):
    def get(self, request):
        top_products = (
            SaleItem.objects.values("product__name")
            .annotate(units=Sum("quantity"), revenue=Sum("subtotal"))
            .order_by("-units")[:5]
        )

        data = []
        for p in top_products:
            data.append(
                {
                    "name": p["product__name"],
                    "units": p["units"],
                    "revenue": float(p["revenue"]),
                    "trend": "up",  # Simplified
                }
            )
        return Response(data)
