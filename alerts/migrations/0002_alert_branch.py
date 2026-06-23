from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0001_initial"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="alert",
            name="branch",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.CASCADE, related_name="alerts", to="inventory.branch"),
        ),
    ]
