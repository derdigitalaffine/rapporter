from django.db import migrations, models


def backfill_positions(apps, schema_editor):
    ShoppingList = apps.get_model("family", "ShoppingList")
    ShoppingItem = apps.get_model("family", "ShoppingItem")
    for shopping_list in ShoppingList.objects.all().iterator():
        rows = list(ShoppingItem.objects.filter(shopping_list=shopping_list).order_by("created_at", "id"))
        for index, row in enumerate(rows, start=1):
            row.position = index * 1000
        if rows:
            ShoppingItem.objects.bulk_update(rows, ["position"])


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0225_pin_interactions"),
    ]

    operations = [
        migrations.AddField(
            model_name="shoppingitem",
            name="position",
            field=models.PositiveIntegerField(db_index=True, default=2147483647),
        ),
        migrations.RunPython(backfill_positions, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name="shoppingitem",
            options={"ordering": ["position", "created_at", "id"]},
        ),
    ]
