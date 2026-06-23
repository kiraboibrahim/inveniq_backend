# Generated migration for StockPrediction model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0003_branch_code_branch_manager"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockPrediction",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("prediction_date", models.DateField()),
                ("predicted_stock", models.IntegerField()),
                ("predicted_demand", models.IntegerField()),
                (
                    "model_type",
                    models.CharField(
                        choices=[
                            ("sarima", "SARIMA"),
                            ("prophet", "Prophet"),
                            ("sklearn", "Scikit-learn"),
                        ],
                        max_length=20,
                    ),
                ),
                ("confidence_lower", models.IntegerField(blank=True, null=True)),
                ("confidence_upper", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="stock_predictions",
                        to="inventory.product",
                    ),
                ),
            ],
            options={
                "ordering": ["product", "prediction_date"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="stockprediction",
            unique_together={("product", "prediction_date", "model_type")},
        ),
    ]