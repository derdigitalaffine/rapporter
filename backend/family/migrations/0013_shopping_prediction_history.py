from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def seed_checked_items(apps, schema_editor):
    ShoppingItem = apps.get_model("family", "ShoppingItem")
    ShoppingPurchaseEvent = apps.get_model("family", "ShoppingPurchaseEvent")
    for item in ShoppingItem.objects.filter(checked=True, checked_at__isnull=False).select_related("shopping_list"):
        name = (item.name or "").strip()
        normalized = name.casefold()
        if not normalized:
            continue
        ShoppingPurchaseEvent.objects.get_or_create(
            source_item_id=item.id,
            purchased_at=item.checked_at,
            defaults={
                "family_id": item.shopping_list.family_id,
                "shopping_list_id": item.shopping_list_id,
                "normalized_name": normalized,
                "display_name": name,
                "quantity": item.quantity or "",
                "category": item.category or "",
                "aisle": item.aisle or "",
                "store": item.shopping_list.store or "",
                "purchased_by_id": item.added_by_id,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0012_family_messages"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingPurchaseEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_item_id", models.UUIDField(blank=True, null=True)),
                ("normalized_name", models.CharField(max_length=180)),
                ("display_name", models.CharField(max_length=160)),
                ("quantity", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=80)),
                ("aisle", models.CharField(blank=True, max_length=80)),
                ("store", models.CharField(blank=True, max_length=120)),
                ("purchased_at", models.DateTimeField(db_index=True)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_purchase_events", to="family.family")),
                ("purchased_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_purchase_events", to=settings.AUTH_USER_MODEL)),
                ("shopping_list", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="purchase_events", to="family.shoppinglist")),
            ],
            options={"ordering": ["purchased_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingPredictionFeedback",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("normalized_name", models.CharField(max_length=180)),
                ("action", models.CharField(choices=[("accepted", "Accepted"), ("snoozed", "Snoozed"), ("dismissed", "Dismissed")], default="accepted", max_length=16)),
                ("suppress_until", models.DateTimeField(blank=True, null=True)),
                ("dismiss_count", models.PositiveIntegerField(default=0)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_prediction_feedback", to="family.family")),
            ],
        ),
        migrations.AddIndex(
            model_name="shoppingpurchaseevent",
            index=models.Index(fields=["family", "normalized_name", "purchased_at"], name="fam_purchase_name_time_idx"),
        ),
        migrations.AddIndex(
            model_name="shoppingpurchaseevent",
            index=models.Index(fields=["family", "purchased_at"], name="fam_purchase_time_idx"),
        ),
        migrations.AddConstraint(
            model_name="shoppingpurchaseevent",
            constraint=models.UniqueConstraint(fields=("source_item_id", "purchased_at"), name="fam_purchase_item_time_uniq"),
        ),
        migrations.AddIndex(
            model_name="shoppingpredictionfeedback",
            index=models.Index(fields=["family", "suppress_until"], name="fam_prediction_suppress_idx"),
        ),
        migrations.AddConstraint(
            model_name="shoppingpredictionfeedback",
            constraint=models.UniqueConstraint(fields=("family", "normalized_name"), name="fam_prediction_feedback_uniq"),
        ),
        migrations.RunPython(seed_checked_items, migrations.RunPython.noop),
    ]
