import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0251_routine_task_migration"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingPurchaseStoreContext",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("address_snapshot", models.CharField(blank=True, max_length=240)),
                (
                    "purchase_event",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="store_context",
                        to="family.shoppingpurchaseevent",
                    ),
                ),
                (
                    "shopping_store",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="purchase_event_contexts",
                        to="family.shoppingstore",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="shoppingpurchasestorecontext",
            index=models.Index(fields=["shopping_store", "created_at"], name="shop_purchase_store_idx"),
        ),
    ]
