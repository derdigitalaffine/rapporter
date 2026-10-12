import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('family', '0224_merge_create_preferences_pin_visibility'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PinComment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('body', models.TextField(max_length=2000)),
                ('client_id', models.UUIDField()),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('author', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pin_comments', to=settings.AUTH_USER_MODEL)),
                ('family', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pin_comments', to='family.family')),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='comments', to='family.boardpost')),
            ],
            options={'ordering': ['created_at', 'id']},
        ),
        migrations.CreateModel(
            name='PinCommentMention',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('comment', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mentions', to='family.pincomment')),
                ('membership', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pin_comment_mentions', to='family.membership')),
            ],
        ),
        migrations.CreateModel(
            name='PinReaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('key', models.CharField(choices=[('thumbs_up', 'Passt'), ('heart', 'Herz'), ('joy', 'Freude'), ('celebrate', 'Feiern'), ('seen', 'Gesehen')], max_length=16)),
                ('comment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='family.pincomment')),
                ('membership', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pin_reactions', to='family.membership')),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reactions', to='family.boardpost')),
            ],
        ),
        migrations.CreateModel(
            name='PinInteractionState',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_seen_comment_at', models.DateTimeField(blank=True, null=True)),
                ('muted', models.BooleanField(default=False)),
                ('membership', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pin_interaction_states', to='family.membership')),
                ('pin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='interaction_states', to='family.boardpost')),
            ],
        ),
        migrations.AddConstraint(
            model_name='pincomment',
            constraint=models.UniqueConstraint(fields=('pin', 'author', 'client_id'), name='pin_comment_retry_unique'),
        ),
        migrations.AddIndex(
            model_name='pincomment',
            index=models.Index(fields=['pin', 'created_at'], name='pin_comment_pin_time'),
        ),
        migrations.AddIndex(
            model_name='pincomment',
            index=models.Index(fields=['family', 'created_at'], name='pin_comment_family_time'),
        ),
        migrations.AddConstraint(
            model_name='pincommentmention',
            constraint=models.UniqueConstraint(fields=('comment', 'membership'), name='pin_comment_mention_unique'),
        ),
        migrations.AddConstraint(
            model_name='pinreaction',
            constraint=models.UniqueConstraint(condition=models.Q(('comment__isnull', True)), fields=('pin', 'membership'), name='pin_reaction_card_member_unique'),
        ),
        migrations.AddConstraint(
            model_name='pinreaction',
            constraint=models.UniqueConstraint(condition=models.Q(('comment__isnull', False)), fields=('comment', 'membership'), name='pin_reaction_comment_member_unique'),
        ),
        migrations.AddIndex(
            model_name='pinreaction',
            index=models.Index(fields=['pin', 'key'], name='pin_reaction_pin_key'),
        ),
        migrations.AddIndex(
            model_name='pinreaction',
            index=models.Index(fields=['comment', 'key'], name='pin_reaction_comment_key'),
        ),
        migrations.AddConstraint(
            model_name='pininteractionstate',
            constraint=models.UniqueConstraint(fields=('pin', 'membership'), name='pin_interaction_state_unique'),
        ),
        migrations.AddIndex(
            model_name='pininteractionstate',
            index=models.Index(fields=['membership', 'muted'], name='pin_state_member_muted'),
        ),
    ]
