import io
import json
import urllib.request
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from decouple import config
from django.db.models import Sum
from django.utils import timezone
from huey import crontab
from huey.contrib.djhuey import db_periodic_task, db_task

from alerts.models import Alert
from sales.models import SaleItem

from .models import Branch, Category, Product, PurchaseOrder, Stock
from .models_ai import AiInsight, StockPrediction


def create_alert_and_notify(
    title: str, description: str, branch, severity: str, send_sms: bool = False
):
    """Central helper to create Alert, broadcast WebSocket notification, and send SMS if requested."""
    import logging

    logger = logging.getLogger(__name__)

    existing_alert = None

    # Try to find if there's an existing unresolved alert that matches this product/title/branch.
    if title in ["Out of Stock", "Low Stock Warning", "Product Expiring Soon"]:
        # The product name is always the first part before " is out of stock" or " at "
        parts = description.split(" at ")
        if not parts or len(parts) < 2:
            parts = description.split(" is out of stock")

        if parts and len(parts) > 0:
            product_prefix = parts[0].strip()
            existing_alert = Alert.objects.filter(
                title=title,
                branch=branch,
                is_resolved=False,
                description__startswith=product_prefix,
            ).first()

    if not existing_alert:
        existing_alert = Alert.objects.filter(
            title=title, branch=branch, description=description, is_resolved=False
        ).first()

    if existing_alert:
        created = False
        if (
            existing_alert.description != description
            or existing_alert.severity != severity
        ):
            existing_alert.description = description
            existing_alert.severity = severity
            existing_alert.save(update_fields=["description", "severity", "updated_at"])
            try:
                broadcast_notification(description)
            except Exception as e:
                logger.error(f"Error broadcasting WebSocket notification: {e}")
        alert = existing_alert
    else:
        alert = Alert.objects.create(
            title=title,
            description=description,
            branch=branch,
            severity=severity,
            is_resolved=False,
        )
        created = True
        try:
            broadcast_notification(description)
        except Exception as e:
            logger.error(f"Error broadcasting WebSocket notification: {e}")
        if send_sms:
            notify_managers_via_sms(f"{severity.upper()}: {description}")

    return alert, created


@db_task()
def process_excel_import(file_bytes, branch_id=None):
    import openpyxl

    wb = openpyxl.load_workbook(filename=io.BytesIO(file_bytes), data_only=True)
    sheet = wb.active

    headers = [cell.value.lower().strip() if cell.value else "" for cell in sheet[1]]

    def get_val(row_cells, header_name):
        try:
            idx = headers.index(header_name)
            return row_cells[idx].value
        except ValueError:
            return None

    branch = None
    if branch_id and branch_id != "all":
        try:
            branch = Branch.objects.get(id=branch_id)
        except Branch.DoesNotExist:
            pass

    if not branch:
        branch, _ = Branch.objects.get_or_create(name="Main Branch")

    for r in range(2, sheet.max_row + 1):
        row_cells = sheet[r]
        if all(cell.value is None for cell in row_cells):
            continue

        sku_val = get_val(row_cells, "sku")
        if not sku_val:
            continue
        sku = str(sku_val).strip()

        name = get_val(row_cells, "name") or "Unnamed Product"
        category_name = get_val(row_cells, "category") or "General"

        category, _ = Category.objects.get_or_create(name=str(category_name).strip())

        price_val = get_val(row_cells, "price") or 0.0
        try:
            price = float(price_val)
        except (ValueError, TypeError):
            price = 0.0

        threshold_val = get_val(row_cells, "threshold") or 10
        try:
            threshold = int(threshold_val)
        except (ValueError, TypeError):
            threshold = 10

        description = get_val(row_cells, "description") or ""

        product, _ = Product.objects.update_or_create(
            sku=sku,
            defaults={
                "name": str(name).strip(),
                "category": category,
                "price": price,
                "threshold": threshold,
                "description": str(description).strip(),
            },
        )

        qty_val = get_val(row_cells, "quantity") or 0
        try:
            quantity = int(qty_val)
        except (ValueError, TypeError):
            quantity = 0

        Stock.objects.update_or_create(
            product=product, branch=branch, defaults={"quantity": quantity}
        )


def broadcast_notification(message):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "global_notifications", {"type": "send_notification", "message": message}
    )


@db_task()
def send_sms_async(phone: str, message: str):
    from notifications.sms import send_sms

    send_sms(phone, message)


def notify_managers_via_sms(message: str):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    managers = User.objects.filter(role__in=["admin", "manager"]).exclude(
        phone_number=""
    )
    for mgr in managers:
        send_sms_async.delay(mgr.phone_number, message)


@db_periodic_task(crontab(minute="*"))
def check_stock_levels():
    stocks = Stock.objects.all().select_related("product", "branch")
    for stock in stocks:
        if stock.quantity <= 0:
            create_alert_and_notify(
                title="Out of Stock",
                description=f"{stock.product.name} is out of stock at {stock.branch.name}.",
                branch=stock.branch,
                severity="critical",
            )
        elif stock.quantity <= stock.product.threshold:
            create_alert_and_notify(
                title="Low Stock Warning",
                description=f"{stock.product.name} at {stock.branch.name} is low: {stock.quantity} remaining.",
                branch=stock.branch,
                severity="warning",
            )


@db_periodic_task(crontab(hour="*/12"))
def update_ai_insights():
    """
    Comprehensive AI analysis engine using ML models:
    1. Runs demand forecasting.
    2. Identifies stock depletion risks.
    3. Identifies dead stock.
    4. Identifies pricing optimization opportunities.
    """
    AiInsight.objects.all().delete()
    StockPrediction.objects.all().delete()

    end_date = timezone.now()
    thirty_days_ago = end_date - timedelta(days=30)
    sixty_days_ago = end_date - timedelta(days=60)

    # Batch fetch products with pre-fetched stocks to avoid N+1 query
    products = Product.objects.all().prefetch_related("stocks")

    # O(1) query aggregation: Fetch total sold quantities for all products in past 30 days
    sales_30d = (
        SaleItem.objects.filter(sale__timestamp__range=[thirty_days_ago, end_date])
        .values("product_id")
        .annotate(total=Sum("quantity"))
    )
    sales_30d_map = {item["product_id"]: item["total"] for item in sales_30d}

    # O(1) query aggregation: Fetch all products with sales in past 60 days
    active_products_60d = set(
        SaleItem.objects.filter(sale__timestamp__gte=sixty_days_ago).values_list(
            "product_id", flat=True
        )
    )

    for product in products:
        current_stock = sum(stock.quantity for stock in product.stocks.all())
        total_sold = sales_30d_map.get(product.id, 0)
        avg_daily_sales = total_sold / 30.0

        if avg_daily_sales > 0:
            days_remaining = int(current_stock / avg_daily_sales)
            if days_remaining < 14:
                AiInsight.objects.create(
                    title="Stock Depletion Alert",
                    description=(
                        f"{product.name} is selling ~{avg_daily_sales:.2f} units/day. "
                        f"Estimated out of stock in {days_remaining} days."
                    ),
                    insight_type="depletion",
                    action_text="Create Purchase Order",
                    priority=3 if days_remaining < 7 else 2,
                )

        has_sales = product.id in active_products_60d

        if not has_sales and current_stock > 0:
            AiInsight.objects.create(
                title="Dead Stock Identified",
                description=(
                    f"{product.name} has had zero movement in the last 60 days. "
                    "Consider a clearance promotion."
                ),
                insight_type="dead_stock",
                action_text="Clearance Strategy",
                priority=1,
            )

        if avg_daily_sales > 5 and current_stock < product.threshold:
            AiInsight.objects.create(
                title="Pricing Optimization",
                description=(
                    f"High demand for {product.name} with low stock buffers. "
                    "A 5-10% price increase may optimize margins."
                ),
                insight_type="pricing",
                action_text="Review Pricing",
                priority=2,
            )


@db_periodic_task(crontab(hour="0", minute="0"))
def check_expiring_products():
    """Identify products expiring in the next 30 days and generate alerts."""
    today = timezone.now().date()
    expiry_horizon = today + timedelta(days=30)

    expiring_products = Product.objects.filter(
        expiry_date__range=[today, expiry_horizon]
    ).prefetch_related("stocks__branch")

    alerts_created = 0
    for product in expiring_products:
        for stock in product.stocks.all():
            if stock.quantity > 0:
                description = (
                    f"{product.name} at {stock.branch.name} is expiring soon on "
                    f"{product.expiry_date.strftime('%d/%m/%Y')} "
                    f"({stock.quantity} units remaining)."
                )
                _, created = create_alert_and_notify(
                    title="Product Expiring Soon",
                    description=description,
                    branch=stock.branch,
                    severity="warning",
                    send_sms=True,
                )
                if created:
                    alerts_created += 1

    return {"alerts_created": alerts_created}


def call_openai_structured(messages, schema):
    """Makes a post request to Groq/Gemini/OpenAI using standard urllib to avoid extra package dependencies."""
    provider = config("LLM_PROVIDER", default="groq")
    groq_key = config("GROQ_API_KEY", default=None)
    gemini_key = config(
        "GEMINI_API_KEY", default=config("GOOGLE_API_KEY", default=None)
    )
    openai_key = config("OPENAI_API_KEY", default=None)

    if provider == "groq":
        if not groq_key:
            raise ValueError("GROQ_API_KEY not found in environment or settings")
        url = "https://api.groq.com/openai/v1/chat/completions"
        api_key = groq_key
        model = config("GROQ_MODEL", default="llama-3.3-70b-versatile")
    elif provider == "gemini":
        if not gemini_key:
            raise ValueError(
                "GEMINI_API_KEY or GOOGLE_API_KEY not found in environment or settings"
            )
        url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        api_key = gemini_key
        model = config("GEMINI_MODEL", default="gemini-2.5-flash")
    else:
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found in environment or settings")
        url = "https://api.openai.com/v1/chat/completions"
        api_key = openai_key
        model = config("OPENAI_MODEL", default="gpt-4o-mini")

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    data = {
        "model": model,
        "messages": messages,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "anomalies_schema",
                "strict": True,
                "schema": schema,
            },
        },
    }

    req = urllib.request.Request(
        url, data=json.dumps(data).encode("utf-8"), headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            content = res_json["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception as e:
        raise e


@db_periodic_task(crontab(hour="0", minute="0"))
def detect_daily_loss_anomalies():
    """Daily background task to identify stock loss/theft using OpenAI Structured Outputs."""
    cutoff_date = timezone.now() - timedelta(days=1)

    # 1. Negative Stock Entries (manual adjustments)
    from inventory.models import StockEntry

    negative_entries = StockEntry.objects.filter(
        created_at__gte=cutoff_date, quantity__lt=0
    ).select_related("product", "branch")

    adjustments = []
    for entry in negative_entries:
        adjustments.append(
            {
                "product_sku": entry.product.sku,
                "product_name": entry.product.name,
                "branch_id": entry.branch.id,
                "branch_name": entry.branch.name,
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
                        "branch_id": po.branch.id,
                        "branch_name": po.branch.name,
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

    # 3. Ghost Stocks
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
                    "branch_id": s.branch.id,
                    "branch_name": s.branch.name,
                    "quantity_on_hand": s.quantity,
                    "estimated_value": s.quantity * float(s.product.price or 0.0),
                }
            )

    # 4. Off-Hours Adjustments
    off_hours_entries = []
    all_entries = StockEntry.objects.filter(created_at__gte=cutoff_date).select_related(
        "product", "branch"
    )
    for entry in all_entries:
        hour = entry.created_at.astimezone(timezone.get_current_timezone()).hour
        if hour >= 22 or hour < 6:
            off_hours_entries.append(
                {
                    "product_sku": entry.product.sku,
                    "product_name": entry.product.name,
                    "branch_id": entry.branch.id,
                    "branch_name": entry.branch.name,
                    "quantity_change": entry.quantity,
                    "note": entry.note,
                    "hour": hour,
                    "created_at": entry.created_at.isoformat(),
                }
            )

    # 5. Off-Hours Sales
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
                    "branch_id": item.sale.branch.id,
                    "branch_name": item.sale.branch.name,
                    "quantity": item.quantity,
                    "total_amount": float(item.subtotal),
                    "hour": hour,
                    "timestamp": item.sale.timestamp.isoformat(),
                }
            )

    raw_logs = {
        "negative_stock_adjustments": adjustments,
        "receiving_discrepancies": po_discrepancies,
        "potential_ghost_stocks": ghost_stocks,
        "off_hours_stock_adjustments": off_hours_entries,
        "off_hours_sales": off_hours_sales,
    }

    if not (
        adjustments
        or po_discrepancies
        or ghost_stocks
        or off_hours_entries
        or off_hours_sales
    ):
        return {"status": "No logs to analyze"}

    prompt = (
        "You are an expert AI inventory forensics analyst. "
        "Analyze the provided daily stock adjustments, sales transactions, purchase orders, and temporal logs "
        "to detect stock loss, theft, transit shrinkage, ghost stock, or unauthorized off-hours activity. "
        "Provide a list of structured alerts for the manager. Be objective and prioritize high-value discrepancies."
    )

    schema = {
        "type": "object",
        "properties": {
            "anomalies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {
                            "type": "string",
                            "enum": ["critical", "warning", "info"],
                        },
                        "branch_id": {"type": "integer"},
                    },
                    "required": ["title", "description", "severity", "branch_id"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["anomalies"],
        "additionalProperties": False,
    }

    messages = [
        {"role": "system", "content": prompt},
        {
            "role": "user",
            "content": f"Here is the raw logs data:\n{json.dumps(raw_logs)}",
        },
    ]

    try:
        result = call_openai_structured(messages, schema)
        anomalies = result.get("anomalies", [])

        alerts_created = 0
        for anomaly in anomalies:
            try:
                branch = Branch.objects.get(id=anomaly["branch_id"])
            except Branch.DoesNotExist:
                branch = Branch.objects.first()
                if not branch:
                    continue

            _, created = create_alert_and_notify(
                title=anomaly["title"],
                description=anomaly["description"],
                branch=branch,
                severity=anomaly["severity"],
                send_sms=(anomaly["severity"] in ["critical", "warning"]),
            )
            if created:
                alerts_created += 1

        return {
            "status": "success",
            "anomalies_detected": len(anomalies),
            "alerts_created": alerts_created,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
