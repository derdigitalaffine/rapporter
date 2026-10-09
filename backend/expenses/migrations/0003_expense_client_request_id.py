from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("expenses", "0002_expenseshare_split_value")]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="client_request_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_request_id__isnull", False)),
                fields=("family", "created_by", "client_request_id"),
                name="expense_client_request_uniq",
            ),
        ),
    ]
