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
        migrations.RemoveConstraint(
            model_name='conversation',
            name='chat_conversation_scope',
        ),
        migrations.AddConstraint(
            model_name='conversation',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('family__isnull', True), ('friendship__isnull', False), ('kind', 'direct')), models.Q(('friendship__isnull', True), ('kind', 'group')), _connector='OR'), name='chat_conversation_scope'),
        ),
        migrations.AddConstraint(
            model_name='conversation',
            constraint=models.UniqueConstraint(condition=models.Q(('family__isnull', False)), fields=('family',), name='chat_family_conversation_unique'),
        ),
    ]
