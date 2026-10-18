from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0243_shopping_store_location_reference"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppingsessionactivity",
            name="client_stream",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="shoppingsessionactivity",
            name="client_sequence",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shoppingsessionactivity",
            name="mutation_id",
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="shoppingsessionactivity",
            constraint=models.UniqueConstraint(
                condition=models.Q(("client_sequence__isnull", False), ("client_stream__gt", "")),
                fields=("session", "client_stream", "client_sequence"),
                name="shop_activity_client_seq_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="shoppingsessionactivity",
            constraint=models.UniqueConstraint(
                condition=models.Q(("mutation_id__isnull", False)),
                fields=("session", "mutation_id"),
                name="shop_activity_mutation_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="shoppingsessionactivity",
            index=models.Index(
                fields=["session", "client_stream", "client_sequence"],
                name="shop_activity_client_idx",
            ),
        ),
    ]
