from datetime import timedelta

from django.db.models import F, Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from alerts.models import Alert
from sales.models import Sale, SaleItem

from .models import Branch, Product, Stock
from .models_ai import AiInsight, StockPrediction


class StockDepletionForecastView(APIView):
    def get(self, request):
        sku = request.query_params.get("sku")
        if not sku:
            product = Product.objects.all().first()
        else:
            product = Product.objects.filter(sku=sku).first()

        if not product:
            return Response(
                {
                    "product_name": "",
                    "current_stock": 0,
                    "avg_daily_sales": 0.0,
                    "days_remaining": None,
                    "projection": [],
                }
            )

        current_stock = (
            Stock.objects.filter(product=product).aggregate(total=Sum("quantity"))[
                "total"
            ]
            or 0
        )

        stored_predictions = list(
            StockPrediction.objects.filter(product=product)
            .order_by("prediction_date")
            .values(
                "prediction_date",
                "predicted_stock",
                "predicted_demand",
                "confidence_lower",
                "confidence_upper",
                "model_type",
            )
        )

        if stored_predictions:
            avg_daily_sales = stored_predictions[0]["predicted_demand"] or 0
            projection = [
                {
                    "day": f"Day {i + 1}",
                    "predicted": p["predicted_stock"],
                    "confidence_lower": p["confidence_lower"],
                    "confidence_upper": p["confidence_upper"],
                }
                for i, p in enumerate(stored_predictions[:7])
            ]
            days_remaining = (
                int(current_stock / avg_daily_sales) if avg_daily_sales > 0 else None
            )
        else:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)

            total_sold = (
                SaleItem.objects.filter(
                    product=product, sale__timestamp__range=[start_date, end_date]
                ).aggregate(total=Sum("quantity"))["total"]
                or 0
            )

            avg_daily_sales = total_sold / 30.0

            projection = []
            temp_stock = current_stock

            for i in range(7, 0, -1):
                date = end_date - timedelta(days=i)
                actual_sold = (
                    SaleItem.objects.filter(
                        product=product, sale__timestamp__date=date.date()
                    ).aggregate(total=Sum("quantity"))["total"]
                    or 0
                )

                projection.append(
                    {
                        "day": f"Day {7 - i + 1}",
                        "actual": temp_stock,
                        "predicted": temp_stock,
                    }
                )
                temp_stock = max(0, temp_stock - actual_sold)

            for i in range(1, 8):
                projection.append(
                    {
                        "day": f"Day {7 + i}",
                        "predicted": max(0, temp_stock - (avg_daily_sales * i)),
                    }
                )

            days_remaining = (
                int(temp_stock / avg_daily_sales) if avg_daily_sales > 0 else None
            )

        return Response(
            {
                "product_name": product.name,
                "current_stock": current_stock,
                "avg_daily_sales": round(avg_daily_sales, 2),
                "days_remaining": days_remaining,
                "projection": projection,
                "predictions_from_ml": bool(stored_predictions),
            }
        )


class AiInsightSerializer(serializers.ModelSerializer):
    actionText = serializers.CharField(source="action_text")

    class Meta:
        model = AiInsight
        fields = ["title", "description", "insight_type", "actionText", "priority"]


class AiInsightsView(APIView):
    def get(self, request):
        insights = AiInsight.objects.all()
        serializer = AiInsightSerializer(insights, many=True)
        return Response(serializer.data)


class DashboardSummaryView(APIView):
    def get(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        total_products = Product.objects.count()

        stock_value = (
            Stock.objects.aggregate(total=Sum(F("quantity") * F("product__price")))[
                "total"
            ]
            or 0
        )

        low_stock_items = Stock.objects.filter(
            quantity__lte=F("product__threshold"), quantity__gt=0
        ).count()
        out_of_stock_items = Stock.objects.filter(quantity=0).count()

        today_sales = (
            Sale.objects.filter(timestamp__range=[today_start, now]).aggregate(
                total=Sum("total_amount")
            )["total"]
            or 0
        )

        yesterday_start = today_start - timedelta(days=1)
        yesterday_sales = (
            Sale.objects.filter(
                timestamp__range=[yesterday_start, today_start - timedelta(seconds=1)]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        sales_trend = (
            ((today_sales - yesterday_sales) / yesterday_sales * 100)
            if yesterday_sales > 0
            else 0.0
        )

        return Response(
            {
                "totalProducts": total_products,
                "stockValue": float(stock_value),
                "lowStockItems": low_stock_items + out_of_stock_items,
                "todaySales": float(today_sales),
                "salesTrend": round(sales_trend, 1),
            }
        )


class BranchKpisView(APIView):
    def get(self, request):
        now = timezone.now()
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        prev_month_end = current_month_start - timedelta(seconds=1)
        prev_month_start = prev_month_end.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        branches = []
        for branch in Branch.objects.all():
            current_revenue = (
                Sale.objects.filter(
                    branch=branch, timestamp__range=[current_month_start, now]
                ).aggregate(total=Sum("total_amount"))["total"]
                or 0
            )

            prev_revenue = (
                Sale.objects.filter(
                    branch=branch, timestamp__range=[prev_month_start, prev_month_end]
                ).aggregate(total=Sum("total_amount"))["total"]
                or 0
            )

            trend = (
                ((current_revenue - prev_revenue) / prev_revenue * 100)
                if prev_revenue > 0
                else 0.0
            )

            stock_value = (
                Stock.objects.filter(branch=branch).aggregate(
                    total=Sum(F("quantity") * F("product__price"))
                )["total"]
                or 0
            )

            branches.append(
                {
                    "id": branch.id,
                    "name": branch.name,
                    "code": branch.code,
                    "location": branch.location,
                    "manager": branch.manager,
                    "revenue": float(current_revenue),
                    "trend": round(trend, 1),
                    "stockValue": float(stock_value),
                    "activeAlerts": Alert.objects.filter(
                        is_resolved=False, branch=branch
                    ).count(),
                }
            )

        return Response(branches)


class BranchDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()
    location = serializers.CharField()
    manager = serializers.CharField()
    revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    trend = serializers.FloatField()
    stockValue = serializers.DecimalField(max_digits=15, decimal_places=2)
    activeAlerts = serializers.IntegerField()
    alerts = serializers.ListField(child=serializers.DictField())
    topItems = serializers.ListField(child=serializers.DictField())


class BranchDetailView(APIView):
    def get(self, request, pk):
        try:
            branch = Branch.objects.get(pk=pk)
        except Branch.DoesNotExist:
            return Response({"error": "Branch not found"}, status=404)

        now = timezone.now()
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        prev_month_end = current_month_start - timedelta(seconds=1)
        prev_month_start = prev_month_end.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        current_revenue = (
            Sale.objects.filter(
                branch=branch, timestamp__range=[current_month_start, now]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        prev_revenue = (
            Sale.objects.filter(
                branch=branch, timestamp__range=[prev_month_start, prev_month_end]
            ).aggregate(total=Sum("total_amount"))["total"]
            or 0
        )

        trend = (
            ((current_revenue - prev_revenue) / prev_revenue * 100)
            if prev_revenue > 0
            else 0.0
        )

        stock_value = (
            Stock.objects.filter(branch=branch).aggregate(
                total=Sum(F("quantity") * F("product__price"))
            )["total"]
            or 0
        )

        unresolved_alerts = Alert.objects.filter(is_resolved=False, branch=branch)[:10]
        alerts = [{"title": a.title, "severity": a.severity} for a in unresolved_alerts]

        top_items = (
            SaleItem.objects.filter(sale__branch=branch)
            .values("product__name")
            .annotate(units=Sum("quantity"))
            .order_by("-units")[:5]
        )

        top_items_list = [
            {"name": item["product__name"], "units": item["units"]}
            for item in top_items
        ]

        data = {
            "id": branch.id,
            "name": branch.name,
            "code": branch.code,
            "location": branch.location,
            "manager": branch.manager,
            "revenue": current_revenue,
            "trend": round(trend, 1),
            "stockValue": stock_value,
            "activeAlerts": Alert.objects.filter(
                is_resolved=False, branch=branch
            ).count(),
            "alerts": alerts,
            "topItems": top_items_list,
        }

        serializer = BranchDetailSerializer(data)
        return Response(serializer.data)


class StockHistoryView(APIView):
    def get(self, request):
        product_id = request.query_params.get("product_id")
        if not product_id:
            return Response({"error": "product_id is required"}, status=400)

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=404)

        now = timezone.now()
        start_date = now - timedelta(days=30)

        # Get current total stock across all branches as the anchor
        current_total = (
            Stock.objects.filter(product=product).aggregate(total=Sum("quantity"))[
                "total"
            ]
            or 0
        )

        # Get all StockEntry changes in the last 30 days
        # (newest first so we can walk backwards)
        entries = list(
            product.entries.filter(created_at__gte=start_date)
            .order_by("created_at")
            .values("created_at", "quantity", "branch__name")
        )

        # Also get sales deductions in the last 30 days
        from sales.models import SaleItem

        sale_items = list(
            SaleItem.objects.filter(product=product, sale__timestamp__gte=start_date)
            .order_by("sale__timestamp")
            .values("sale__timestamp", "quantity")
        )

        # Build a map of date → net change
        from collections import defaultdict

        daily_net = defaultdict(int)

        for entry in entries:
            day = entry["created_at"].date()
            daily_net[day] += entry["quantity"]

        for item in sale_items:
            day = item["sale__timestamp"].date()
            daily_net[day] -= item["quantity"]

        # Walk forward from 30 days ago, reconstructing running stock
        # Start from current stock and work backwards to find starting point
        starting_stock = current_total
        for d in range(30):
            day = (now - timedelta(days=d)).date()
            starting_stock -= daily_net.get(day, 0)

        # Now walk forward day by day
        data = []
        running = starting_stock
        for d in range(30):
            day = (start_date + timedelta(days=d + 1)).date()
            running += daily_net.get(day, 0)
            data.append(
                {
                    "date": day.strftime("%d %b"),
                    "stock": max(0, running),
                }
            )

        return Response(data)
