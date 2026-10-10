import hashlib

from django.db import migrations, models


def digest_existing_tokens(apps, schema_editor):
    FamilyInvitation = apps.get_model("family", "FamilyInvitation")
    for invite in FamilyInvitation.objects.exclude(token="").iterator():
        invite.token_digest = hashlib.sha256(invite.token.encode("utf-8")).hexdigest()
        invite.token_version = 0
        invite.save(update_fields=["token_digest", "token_version"])


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0214_boardpost_document_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="familyinvitation",
            name="token_digest",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="familyinvitation",
            name="token_version",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(digest_existing_tokens, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="familyinvitation",
            name="token",
        ),
        migrations.AlterField(
            model_name="familyinvitation",
            name="token_digest",
            field=models.CharField(max_length=64, unique=True),
        ),
        migrations.AlterField(
            model_name="familyinvitation",
            name="token_version",
            field=models.PositiveIntegerField(default=1),
        ),
    ]
