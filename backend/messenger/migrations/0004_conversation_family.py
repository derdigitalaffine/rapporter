from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('family', '0227_birthday_age_preferences'),
        ('messenger', '0003_friendship_family_derived'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='family',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='chat_conversations', to='family.family'),
        ),
        migrations.AddField(
            model_name='conversation',
            name='channel',
            field=models.CharField(choices=[('custom', 'Custom'), ('family', 'Family'), ('system', 'System')], default='custom', max_length=12),
        ),
        migrations.RemoveConstraint(
            model_name='conversation',
            name='chat_conversation_scope',
        ),
        migrations.AddConstraint(
            model_name='conversation',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(kind='direct', friendship__isnull=False, family__isnull=True, channel='custom')
                    | models.Q(kind='group', friendship__isnull=True, family__isnull=True, channel='custom')
                    | models.Q(kind='group', friendship__isnull=True, family__isnull=False, channel__in=['family', 'system'])
                ),
                name='chat_conversation_scope',
            ),
        ),
        migrations.AddConstraint(
            model_name='conversation',
            constraint=models.UniqueConstraint(fields=('family', 'channel'), condition=models.Q(family__isnull=False), name='chat_family_channel_unique'),
        ),
    ]
