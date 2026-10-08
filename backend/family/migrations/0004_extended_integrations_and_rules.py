from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("family", "0003_smart_lists_and_automation")]

    operations = [
        migrations.AlterField(
            model_name="integrationsource",
            name="kind",
            field=models.CharField(
                choices=[
                    ("ics", "ICS/iCal"),
                    ("waste", "Waste calendar"),
                    ("weather", "Weather"),
                    ("warning", "Public warning"),
                    ("messenger", "Messenger"),
                    ("home", "Home automation"),
                    ("transit", "Public transit"),
                    ("school", "School"),
                    ("generic", "Generic"),
                ],
                default="generic",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="automationrule",
            name="trigger_type",
            field=models.CharField(
                choices=[
                    ("waste_tomorrow", "Waste collection tomorrow"),
                    ("weather_frost", "Frost forecast"),
                    ("weather_rain", "Rain forecast"),
                    ("warning_active", "Official warning active"),
                    ("event_upcoming", "Upcoming event"),
                    ("daily", "Daily at time"),
                    ("home_state", "Home Assistant entity state"),
                    ("transit_delay", "Transit delay"),
                    ("task_completed", "Task completed"),
                ],
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="automationrule",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("task_create", "Create task"),
                    ("shopping_add", "Add shopping item"),
                    ("inbox_create", "Create inbox message"),
                    ("home_service", "Call Home Assistant service"),
                ],
                max_length=40,
            ),
        ),
    ]
