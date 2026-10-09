from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="expenseshare",
            name="split_value",
            field=models.DecimalField(blank=True, decimal_places=4, max_digits=12, null=True),
        ),
    ]
