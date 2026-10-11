from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0220_pinboard_adapter_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="loyaltycard",
            name="pass_type",
            field=models.CharField(
                choices=[
                    ("loyalty_card", "Loyalty card"),
                    ("voucher", "Voucher"),
                    ("coupon", "Coupon"),
                    ("ticket", "Ticket"),
                    ("boarding_pass", "Boarding pass"),
                ],
                default="loyalty_card",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="icon_key",
            field=models.CharField(blank=True, default="", max_length=48),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="color_mode",
            field=models.CharField(choices=[("custom", "Custom"), ("auto", "Auto from icon")], default="custom", max_length=12),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="archive_reason",
            field=models.CharField(
                blank=True,
                choices=[("manual", "Manual"), ("used", "Used/redeemed"), ("event_ended", "Event ended")],
                default="",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="restore_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="undo_window_minutes",
            field=models.PositiveSmallIntegerField(default=10),
        ),
        migrations.AddField(
            model_name="loyaltycard",
            name="event_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
