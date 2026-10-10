import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0206_travel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ShoppingStore",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("branch_label", models.CharField(blank=True, max_length=120)),
                ("address", models.CharField(blank=True, max_length=240)),
                ("website_url", models.URLField(blank=True, max_length=500)),
                ("offers_url", models.URLField(blank=True, max_length=500)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_shopping_stores", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_stores", to="family.family")),
            ],
            options={"ordering": ["sort_order", "name", "branch_label", "created_at"]},
        ),
        migrations.AddIndex(
            model_name="shoppingstore",
            index=models.Index(fields=["family", "active", "sort_order"], name="shop_store_family_idx"),
        ),
        migrations.CreateModel(
            name="ShoppingTemplate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("archived", models.BooleanField(default=False)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("created_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_shopping_templates", to=settings.AUTH_USER_MODEL)),
                ("default_store", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="shopping_templates", to="family.shoppingstore")),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="shopping_templates", to="family.family")),
            ],
            options={"ordering": ["archived", "sort_order", "name", "created_at"]},
        ),
        migrations.AddIndex(
            model_name="shoppingtemplate",
            index=models.Index(fields=["family", "archived", "sort_order"], name="shop_tpl_family_idx"),
        ),
        migrations.CreateModel(
            name="ShoppingListStoreProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("shopping_list", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="store_profile_assignment", to="family.shoppinglist")),
                ("store", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="list_assignments", to="family.shoppingstore")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="ShoppingTemplateItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("normalized_name", models.CharField(editable=False, max_length=160)),
                ("quantity", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=80)),
                ("aisle", models.CharField(blank=True, max_length=80)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("position", models.PositiveIntegerField(default=0)),
                ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="family.shoppingtemplate")),
            ],
            options={"ordering": ["position", "created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="shoppingtemplateitem",
            constraint=models.UniqueConstraint(fields=("template", "normalized_name"), name="uniq_shopping_template_item_name"),
        ),
    ]
