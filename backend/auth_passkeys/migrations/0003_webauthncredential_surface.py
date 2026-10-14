from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_passkeys", "0002_webauthnchallenge_context"),
    ]

    operations = [
        migrations.AddField(
            model_name="webauthncredential",
            name="surface",
            field=models.CharField(
                choices=[("app", "App"), ("superadmin", "Superadmin")],
                db_index=True,
                default="app",
                max_length=24,
            ),
        ),
        migrations.RemoveIndex(
            model_name="webauthncredential",
            name="passkey_user_active_idx",
        ),
        migrations.AddIndex(
            model_name="webauthncredential",
            index=models.Index(
                fields=["user", "surface", "revoked_at"],
                name="passkey_user_surface_idx",
            ),
        ),
    ]
