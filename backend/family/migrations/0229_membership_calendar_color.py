from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("family", "0228_action_actioncompletion_actioncommand_actioncapture_and_more")]

    operations = [
        migrations.RunSQL(
            sql="ALTER TABLE family_membership ADD COLUMN calendar_color varchar(7) NOT NULL DEFAULT '';",
            reverse_sql="ALTER TABLE family_membership DROP COLUMN calendar_color;",
        ),
    ]
