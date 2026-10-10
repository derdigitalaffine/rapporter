from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AuthAbuseBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(max_length=64)),
                ("key_hash", models.CharField(max_length=64)),
                ("key_kind", models.CharField(max_length=32)),
                ("window_kind", models.CharField(max_length=16)),
                ("window_seconds", models.PositiveIntegerField()),
                ("window_started_at", models.DateTimeField()),
                ("count", models.PositiveIntegerField(default=0)),
                ("penalty_level", models.PositiveSmallIntegerField(default=0)),
                ("blocked_until", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [models.Index(fields=["scope", "key_hash"], name="auth_abuse_scope_key")],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("scope", "key_hash", "window_kind"),
                        name="auth_abuse_bucket_unique",
                    )
                ],
            },
        )
    ]
