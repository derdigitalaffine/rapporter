import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0244_shopping_activity_client_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingItemCreateReceipt",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("mutation_id", models.UUIDField()),
                ("item", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="create_receipt", to="family.shoppingitem")),
                ("shopping_list", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="item_create_receipts", to="family.shoppinglist")),
            ],
            options={
                "indexes": [models.Index(fields=["shopping_list", "mutation_id"], name="shop_item_create_mut_idx")],
                "constraints": [models.UniqueConstraint(fields=("shopping_list", "mutation_id"), name="shop_item_create_mutation_uniq")],
            },
        ),
    ]
