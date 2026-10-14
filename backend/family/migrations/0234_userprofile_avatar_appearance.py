from django.db import migrations, models


PALETTE = (
    "#2F6F73", "#3F6FA8", "#6B5FA7", "#8A5E8D",
    "#A65353", "#A86E35", "#8A7A32", "#4F7B45",
    "#357A68", "#426E8A", "#755B45", "#626A73",
)


def seed_avatar_appearance(apps, schema_editor):
    UserProfile = apps.get_model("family", "UserProfile")
    for profile in UserProfile.objects.all().iterator():
        profile.avatar_mode = "photo" if profile.avatar_key else "initials"
        profile.avatar_color = PALETTE[profile.user_id % len(PALETTE)]
        profile.save(update_fields=["avatar_mode", "avatar_color"])


class Migration(migrations.Migration):
    dependencies = [("family", "0233_calendar_planner_preferences")]

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
        migrations.RunPython(seed_avatar_appearance, migrations.RunPython.noop),
    ]
