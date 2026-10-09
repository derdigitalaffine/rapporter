from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0009_notifications_and_loyalty_cards")]

    operations = [
        migrations.AddField(
            model_name="family",
            name="status",
            field=models.CharField(
                choices=[("active", "Active"), ("suspended", "Suspended")],
                db_index=True,
                default="active",
                max_length=16,
            ),
        ),
    ]
