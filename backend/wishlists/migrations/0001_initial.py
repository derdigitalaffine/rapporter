# Generated for the universal Wishlist Core (#280).
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("family", "0217_merge_trip_invitation"),
    ]

    operations = [
        migrations.CreateModel(
            name="Wishlist",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                ("visibility", models.CharField(choices=[("selected", "Selected"), ("family", "Family")], db_index=True, default="selected", max_length=16)),
                ("active", models.BooleanField(db_index=True, default=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="wishlists_created", to=settings.AUTH_USER_MODEL)),
                ("family", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="wishlists", to="family.family")),
                ("owner_membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="owned_wishlists", to="family.membership")),
            ],
            options={
                "ordering": ["-updated_at", "title"],
                "indexes": [
                    models.Index(fields=["family", "active", "visibility"], name="wishlist_family_vis_idx"),
                    models.Index(fields=["owner_membership", "active"], name="wishlist_owner_active_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WishlistItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=180)),
                ("url", models.URLField(blank=True, max_length=1000)),
                ("note", models.TextField(blank=True)),
                ("priority", models.CharField(blank=True, choices=[("low", "Low"), ("normal", "Normal"), ("high", "High")], max_length=12)),
                ("archived_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="wishlist_items_created", to=settings.AUTH_USER_MODEL)),
                ("wishlist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="wishlists.wishlist")),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [models.Index(fields=["wishlist", "archived_at"], name="wishlist_item_active_idx")],
            },
        ),
        migrations.CreateModel(
            name="WishlistAccess",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="wishlist_access_entries", to="family.membership")),
                ("wishlist", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="access_entries", to="wishlists.wishlist")),
            ],
            options={},
        ),
        migrations.CreateModel(
            name="WishlistReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("reserved", "Reserved"), ("purchased", "Purchased")], db_index=True, default="reserved", max_length=16)),
                ("note", models.CharField(blank=True, max_length=240)),
                ("item", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="reservation", to="wishlists.wishlistitem")),
                ("reserved_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="wishlist_reservations", to="family.membership")),
            ],
            options={
                "indexes": [models.Index(fields=["reserved_by", "status"], name="wishlist_reserver_idx")],
            },
        ),
        migrations.AddConstraint(
            model_name="wishlistaccess",
            constraint=models.UniqueConstraint(fields=("wishlist", "membership"), name="wishlist_access_member_uniq"),
        ),
    ]
