from django.db import migrations, models


def seed_avatar_mode(apps, schema_editor):
    UserProfile = apps.get_model("family", "UserProfile")
    UserProfile.objects.exclude(avatar_key="").update(avatar_mode="photo")


class Migration(migrations.Migration):
    dependencies = [("family", "0234_calendar_planner_preferences")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="avatar_mode",
            field=models.CharField(default="initials", max_length=16),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="avatar_icon_key",
            field=models.CharField(blank=True, max_length=48),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="avatar_color",
            field=models.CharField(blank=True, max_length=7),
        ),
        migrations.RunPython(seed_avatar_mode, migrations.RunPython.noop),
    ]
