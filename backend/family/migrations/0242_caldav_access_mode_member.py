from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('family', '0241_calendar_subscription')]

    operations = [
        migrations.AddField(
            model_name='calendarsubscription',
            name='detail_level',
            field=models.CharField(choices=[('availability', 'Availability only'), ('title', 'Title and time'), ('full', 'Full safe details')], default='title', max_length=16),
        ),
        migrations.AddField(
            model_name='caldavconnection',
            name='access_mode',
            field=models.CharField(choices=[('read', 'Read only'), ('read_write', 'Read and write')], default='read', max_length=16),
        ),
        migrations.AddField(
            model_name='caldavconnection',
            name='calendar_href',
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name='caldavconnection',
            name='member',
            field=models.ForeignKey(blank=True, help_text='Optional family member whose external calendar this connection projects.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='caldav_connections', to='family.membership'),
        ),
        migrations.RemoveConstraint(model_name='caldavconnection', name='caldav_scope_owner_exactly_one'),
        migrations.AddConstraint(
            model_name='caldavconnection',
            constraint=models.CheckConstraint(
                condition=(models.Q(('family__isnull', True), ('member__isnull', True), ('owner__isnull', False), ('scope', 'personal')) | models.Q(('family__isnull', False), ('owner__isnull', True), ('scope', 'family'))),
                name='caldav_scope_owner_exactly_one',
            ),
        ),
        migrations.AddConstraint(
            model_name='caldavconnection',
            constraint=models.UniqueConstraint(condition=models.Q(('member__isnull', False)), fields=('family', 'member'), name='caldav_one_calendar_per_member'),
        ),
    ]
