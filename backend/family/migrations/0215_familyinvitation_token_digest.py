import hashlib

from django.db import migrations


def digest_existing_tokens(apps, schema_editor):
    FamilyInvitation = apps.get_model("family", "FamilyInvitation")
    for invite in FamilyInvitation.objects.exclude(token="").iterator():
        invite.token = hashlib.sha256(invite.token.encode("utf-8")).hexdigest()
        invite.save(update_fields=["token"])


class Migration(migrations.Migration):
    dependencies = [
        ("family", "0214_boardpost_document_kind"),
    ]

    operations = [
        migrations.RunPython(digest_existing_tokens, migrations.RunPython.noop),
    ]
