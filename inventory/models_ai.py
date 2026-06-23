from django.db import models


class StockPrediction(models.Model):
    product = models.ForeignKey(
        "inventory.Product", on_delete=models.CASCADE, related_name="stock_predictions"
    )
    prediction_date = models.DateField()
    predicted_stock = models.IntegerField()
    predicted_demand = models.IntegerField()
    model_type = models.CharField(
        max_length=20,
        choices=[
            ("sarima", "SARIMA"),
            ("prophet", "Prophet"),
            ("sklearn", "Scikit-learn"),
        ],
    )
    confidence_lower = models.IntegerField(null=True, blank=True)
    confidence_upper = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product", "prediction_date"]
        unique_together = ("product", "prediction_date", "model_type")

    def __str__(self):
        return f"{self.product.name} - {self.prediction_date} ({self.model_type})"


class AiInsight(models.Model):
    INSIGHT_TYPES = [
        ("depletion", "Stock Depletion"),
        ("dead_stock", "Dead Stock"),
        ("pricing", "Pricing Optimization"),
        ("anomaly", "Sales Anomaly"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    action_text = models.CharField(max_length=50, default="View Details")
    priority = models.IntegerField(default=1)  # 1: Low, 2: Medium, 3: High
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-priority", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.insight_type})"
