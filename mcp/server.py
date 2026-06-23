import json
import logging
import os
import sys

# Set up logging to stderr so it doesn't pollute standard outputs
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mcp_server")

# Initialize Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

# Load environment variables from the root .env file
from dotenv import load_dotenv

load_dotenv(
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
)

try:
    import django

    django.setup()
except Exception as e:
    logger.error(f"Failed to setup Django: {e}")
    sys.exit(1)

from datetime import timedelta

from django.db.models import Avg, Q, Sum
from django.utils import timezone

from inventory.models import (
    Branch,
    Category,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    Stock,
    StockEntry,
)

# Import the official FastMCP class
from mcp.server.fastmcp import FastMCP
from sales.models import SaleItem
from stakeholders.models import Supplier

mcp = FastMCP("InvenIQ MCP Server", host="0.0.0.0", port=8001)


@mcp.tool()
def run_demand_forecast(sku: str, days: int = 30) -> str:
    """Calculates detailed historical sales metrics, seasonality, and trends for a product SKU to help predict future demand."""
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return json.dumps({"error": f"Product with SKU '{sku}' not found."})

    cutoff_date = timezone.now() - timedelta(days=days)
    sales = SaleItem.objects.filter(product=product, sale__timestamp__gte=cutoff_date)

    total_qty_sold = sales.aggregate(total=Sum("quantity"))["total"] or 0
    avg_daily_sales = total_qty_sold / days

    weekday_sales = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}  # Mon-Sun
    for sale_item in sales.select_related("sale"):
        wd = sale_item.sale.timestamp.weekday()
        weekday_sales[wd] += sale_item.quantity

    current_stock = sum(s.quantity for s in product.stocks.all())
    days_remaining = (
        int(current_stock / avg_daily_sales) if avg_daily_sales > 0 else float("inf")
    )

    res = {
        "sku": sku,
        "product_name": product.name,
        "current_stock": current_stock,
        "low_stock_threshold": product.threshold,
        "analysis_period_days": days,
        "total_units_sold": total_qty_sold,
        "average_daily_sales": round(avg_daily_sales, 2),
        "estimated_days_stock_remaining": days_remaining,
        "weekly_seasonality_totals": {
            "Monday": weekday_sales[0],
            "Tuesday": weekday_sales[1],
            "Wednesday": weekday_sales[2],
            "Thursday": weekday_sales[3],
            "Friday": weekday_sales[4],
            "Saturday": weekday_sales[5],
            "Sunday": weekday_sales[6],
        },
    }
    return json.dumps(res, indent=2)


@mcp.tool()
def recommend_suppliers(sku: str) -> str:
    """Evaluates fulfillment ratings, historical purchase costs, and delivery history to recommend the best supplier for a product SKU."""
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return json.dumps({"error": f"Product with SKU '{sku}' not found."})

    primary = product.primary_supplier
    active_suppliers = Supplier.objects.filter(status="active")

    recommendations = []
    for supplier in active_suppliers:
        avg_cost = PurchaseOrderItem.objects.filter(
            purchase_order__supplier=supplier, product=product
        ).aggregate(avg=Avg("unit_cost"))["avg"]

        avg_cost_val = float(avg_cost) if avg_cost else float(product.cost_price or 0.0)

        score = 0.7 * supplier.fulfillment_rating
        if avg_cost_val > 0:
            score += 0.3 * (100 * float(product.price) / avg_cost_val)

        recommendations.append(
            {
                "supplier_id": supplier.id,
                "name": supplier.name,
                "fulfillment_rating": supplier.fulfillment_rating,
                "historical_average_cost": round(avg_cost_val, 2),
                "calculated_recommendation_score": round(score, 1),
                "is_primary": primary == supplier if primary else False,
            }
        )

    recommendations.sort(
        key=lambda x: x["calculated_recommendation_score"], reverse=True
    )

    res = {
        "sku": sku,
        "product_name": product.name,
        "primary_supplier": {
            "id": primary.id,
            "name": primary.name,
            "fulfillment_rating": primary.fulfillment_rating,
        }
        if primary
        else None,
        "recommendations": recommendations,
    }
    return json.dumps(res, indent=2)


@mcp.tool()
def detect_theft_anomalies(days: int = 30) -> str:
    """Gathers raw sales, manual stock adjustments, PO intake logs, and off-hours activity to analyze for shrinkage, transit loss, or theft."""
    cutoff_date = timezone.now() - timedelta(days=days)

    # 1. Negative Manual Stock Adjustments (Loss/Shrinkage)
    negative_entries = StockEntry.objects.filter(
        created_at__gte=cutoff_date, quantity__lt=0
    ).select_related("product", "branch")

    adjustments = []
    for entry in negative_entries:
        adjustments.append(
            {
                "entry_id": entry.id,
                "product_sku": entry.product.sku,
                "product_name": entry.product.name,
                "branch": entry.branch.name,
                "quantity_change": entry.quantity,
                "note": entry.note,
                "created_at": entry.created_at.isoformat(),
                "estimated_value": abs(entry.quantity)
                * float(entry.product.cost_price or 0.0),
            }
        )

    # 2. Purchase Order Receipt Discrepancies
    received_pos = PurchaseOrder.objects.filter(
        updated_at__gte=cutoff_date, status="received"
    ).prefetch_related("items__product", "branch", "supplier")

    po_discrepancies = []
    for po in received_pos:
        for item in po.items.all():
            # Find positive stock entry adjustments for the same product at the same branch
            # created near the PO receipt time (+/- 2 hours)
            entries = StockEntry.objects.filter(
                product=item.product,
                branch=po.branch,
                created_at__range=[
                    po.updated_at - timedelta(hours=2),
                    po.updated_at + timedelta(hours=2),
                ],
                quantity__gt=0,
            )
            added_qty = sum(e.quantity for e in entries)
            if added_qty < item.quantity:
                po_discrepancies.append(
                    {
                        "po_id": po.id,
                        "supplier": po.supplier.name,
                        "branch": po.branch.name,
                        "product_sku": item.product.sku,
                        "product_name": item.product.name,
                        "ordered_qty": item.quantity,
                        "added_qty": added_qty,
                        "shortage": item.quantity - added_qty,
                        "estimated_value_loss": (item.quantity - added_qty)
                        * float(item.product.cost_price or 0.0),
                        "received_date": po.updated_at.isoformat(),
                    }
                )

    # 3. Potential Ghost Stocks (positive stock on hand with zero sales velocity)
    stocks = Stock.objects.filter(quantity__gt=0).select_related("product", "branch")
    ghost_stocks = []
    for s in stocks:
        has_sales = SaleItem.objects.filter(
            product=s.product, sale__branch=s.branch, sale__timestamp__gte=cutoff_date
        ).exists()

        if not has_sales:
            ghost_stocks.append(
                {
                    "product_sku": s.product.sku,
                    "product_name": s.product.name,
                    "branch": s.branch.name,
                    "quantity_on_hand": s.quantity,
                    "estimated_stagnant_value": s.quantity
                    * float(s.product.price or 0.0),
                }
            )

    # 4. Off-Hours Activity (Adjustments & Sales made between 10 PM and 6 AM)
    off_hours_entries = []
    all_entries = StockEntry.objects.filter(created_at__gte=cutoff_date).select_related(
        "product", "branch"
    )
    for entry in all_entries:
        hour = entry.created_at.astimezone(timezone.get_current_timezone()).hour
        if hour >= 22 or hour < 6:
            off_hours_entries.append(
                {
                    "entry_id": entry.id,
                    "product_sku": entry.product.sku,
                    "product_name": entry.product.name,
                    "branch": entry.branch.name,
                    "quantity_change": entry.quantity,
                    "note": entry.note,
                    "hour": hour,
                    "created_at": entry.created_at.isoformat(),
                }
            )

    off_hours_sales = []
    all_sales = SaleItem.objects.filter(
        sale__timestamp__gte=cutoff_date
    ).select_related("product", "sale__branch")
    for item in all_sales:
        hour = item.sale.timestamp.astimezone(timezone.get_current_timezone()).hour
        if hour >= 22 or hour < 6:
            off_hours_sales.append(
                {
                    "sale_id": item.sale.id,
                    "product_sku": item.product.sku,
                    "product_name": item.product.name,
                    "branch": item.sale.branch.name,
                    "quantity": item.quantity,
                    "total_amount": float(item.subtotal),
                    "hour": hour,
                    "timestamp": item.sale.timestamp.isoformat(),
                }
            )

    res = {
        "period_checked_days": days,
        "negative_stock_adjustments": adjustments,
        "receiving_discrepancies": po_discrepancies,
        "potential_ghost_stocks": ghost_stocks,
        "off_hours_stock_adjustments": off_hours_entries,
        "off_hours_sales": off_hours_sales,
    }
    return json.dumps(res, indent=2)


@mcp.tool()
def generate_restock_po(sku: str, quantity: int, branch_id: int = 1) -> str:
    """Drafts a purchase order (PO) for restocking a product from its primary or recommended supplier."""
    try:
        product = Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        return json.dumps({"error": f"Product with SKU '{sku}' not found."})

    try:
        branch = Branch.objects.get(id=branch_id)
    except Branch.DoesNotExist:
        return json.dumps({"error": f"Branch with ID {branch_id} not found."})

    supplier = product.primary_supplier
    if not supplier:
        active_sups = list(
            Supplier.objects.filter(status="active").order_by("-fulfillment_rating")
        )
        if active_sups:
            supplier = active_sups[0]
        else:
            return json.dumps(
                {"error": "No active suppliers available to generate PO."}
            )

    try:
        po = PurchaseOrder.objects.create(
            supplier=supplier, branch=branch, status="draft"
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=po,
            product=product,
            quantity=quantity,
            unit_cost=product.cost_price or 0.00,
        )

        res = {
            "success": True,
            "po_id": po.id,
            "supplier_name": supplier.name,
            "branch_name": branch.name,
            "status": po.status,
            "product_name": product.name,
            "quantity": quantity,
            "unit_cost": float(item.unit_cost),
            "estimated_total_cost": quantity * float(item.unit_cost),
        }
        return json.dumps(res, indent=2)
    except Exception as e:
        logger.error(f"Error creating PO: {e}")
        return json.dumps({"error": f"Failed to create Purchase Order: {str(e)}"})


@mcp.tool()
def search_products(query: str) -> str:
    """Searches for products by name, SKU, or description and returns a list of matches with their SKUs, names, and current prices."""
    products = Product.objects.filter(
        Q(name__icontains=query)
        | Q(sku__icontains=query)
        | Q(description__icontains=query)
    ).prefetch_related("stocks")[:10]

    results = []
    for p in products:
        total_stock = sum(s.quantity for s in p.stocks.all())
        results.append(
            {
                "sku": p.sku,
                "name": p.name,
                "category": p.category.name if p.category else None,
                "price": float(p.price),
                "current_total_stock": total_stock,
                "description": p.description,
            }
        )

    return json.dumps(results, indent=2)


@mcp.tool()
def list_products(category_id: int = None, limit: int = 15) -> str:
    """Lists available products in the inventory, optionally filtered by category ID. Useful when the user wants to browse or pick from a list of products."""
    try:
        queryset = Product.objects.all().prefetch_related("stocks")
        if category_id is not None:
            queryset = queryset.filter(category_id=category_id)
        products = queryset[:limit]

        results = []
        for p in products:
            total_stock = sum(s.quantity for s in p.stocks.all())
            results.append(
                {
                    "sku": p.sku,
                    "name": p.name,
                    "category": p.category.name if p.category else None,
                    "price": float(p.price),
                    "current_total_stock": total_stock,
                    "description": p.description,
                }
            )
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to list products: {str(e)}"})


@mcp.tool()
def list_categories() -> str:
    """Lists all product categories with their IDs and names. Useful for discovering category IDs to filter product lists."""
    try:
        categories = Category.objects.all()
        results = []
        for c in categories:
            results.append({"id": c.id, "name": c.name})
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to list categories: {str(e)}"})


if __name__ == "__main__":
    # Support running as a standalone SSE daemon
    mcp.run(transport="sse")
