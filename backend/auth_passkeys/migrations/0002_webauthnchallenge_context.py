from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auth_passkeys", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="webauthnchallenge",
            name="context",
            field=models.CharField(
                choices=[("app", "App"), ("superadmin", "Superadmin")],
                default="app",
                max_length=24,
            ),
        ),
        migrations.RemoveIndex(
            model_name="webauthnchallenge",
            name="passkey_chal_exp_idx",
        ),
        migrations.AddIndex(
            model_name="webauthnchallenge",
            index=models.Index(
                fields=["ceremony", "context", "expires_at"],
                name="passkey_chal_ctx_exp_idx",
            ),
        ),
    ]
