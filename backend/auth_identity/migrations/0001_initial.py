from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EmailIdentity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("primary", "Primary"), ("pending", "Pending")], default="primary", max_length=16)),
                ("email", models.EmailField(max_length=254)),
                ("email_normalized", models.CharField(max_length=254, unique=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("verification_sent_at", models.DateTimeField(blank=True, null=True)),
                ("verification_version", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="email_identities", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="emailidentity",
            constraint=models.UniqueConstraint(fields=("user", "kind"), name="auth_identity_user_kind_unique"),
        ),
        migrations.AddIndex(
            model_name="emailidentity",
            index=models.Index(fields=["user", "kind"], name="auth_identity_user_kind"),
        ),
    ]
