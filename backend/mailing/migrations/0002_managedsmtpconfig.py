from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("mailing", "0001_initial")]
    operations = [
        migrations.CreateModel(
            name="ManagedSmtpConfig",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ("enabled", models.BooleanField(default=False)),
                ("host", models.CharField(blank=True, default="", max_length=253)),
                ("port", models.PositiveIntegerField(default=587)),
                ("username", models.CharField(blank=True, default="", max_length=254)),
                ("password_encrypted", models.TextField(blank=True, default="")),
                ("security", models.CharField(choices=[("starttls", "STARTTLS"), ("ssl", "TLS/SSL"), ("plain", "Plain")], default="starttls", max_length=16)),
                ("timeout", models.PositiveSmallIntegerField(default=10)),
                ("from_email", models.EmailField(blank=True, default="", max_length=254)),
                ("reply_to", models.EmailField(blank=True, default="", max_length=254)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
