# Generated for FamilyOS messenger family-member hotfix

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('messenger', '0002_chatmessage_payload_digest'),
    ]

    operations = [
        migrations.AddField(
            model_name='friendship',
            name='family_derived',
            field=models.BooleanField(default=False),
        ),
    ]
