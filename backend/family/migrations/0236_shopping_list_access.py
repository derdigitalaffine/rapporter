# Generated manually for the additive ShoppingList access contract.
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0235_userprofile_avatar_appearance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingListAccess",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("visibility", models.CharField(choices=[("family", "Whole family"), ("private", "Private"), ("selected", "Selected people")], db_index=True, default="family", max_length=16)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_shopping_list_access", to=settings.AUTH_USER_MODEL)),
                ("shopping_list", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="access_settings", to="family.shoppinglist")),
                ("responsible_members", models.ManyToManyField(blank=True, related_name="responsible_shopping_lists", to="family.membership")),
                ("visible_members", models.ManyToManyField(blank=True, related_name="visible_shopping_lists", to="family.membership")),
            ],
        ),
    ]
