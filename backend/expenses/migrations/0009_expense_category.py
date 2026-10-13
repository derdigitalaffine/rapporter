from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0008_expense_frozen_fx")]
    operations = [migrations.AddField(model_name="expense", name="category", field=models.CharField(max_length=80, blank=True))]
