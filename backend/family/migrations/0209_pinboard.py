from django.db import migrations, models


def seed_pinboard(apps, schema_editor):
    BoardPost = apps.get_model('family', 'BoardPost')
    BoardImage = apps.get_model('family', 'BoardImage')
    family_ids = BoardPost.objects.order_by().values_list('family_id', flat=True).distinct()
    for family_id in family_ids:
        rows = list(BoardPost.objects.filter(family_id=family_id).order_by('-created_at', '-id'))
        image_post_ids = set(BoardImage.objects.filter(post_id__in=[row.id for row in rows]).values_list('post_id', flat=True))
        for index, row in enumerate(rows):
            row.position = index * 1000
            row.kind = 'photo' if row.id in image_post_ids else 'note'
        BoardPost.objects.bulk_update(rows, ['position', 'kind'])


class Migration(migrations.Migration):
    dependencies = [('family', '0208_notification_badge_state')]

    operations = [
        migrations.AddField(
            model_name='boardpost',
            name='kind',
            field=models.CharField(choices=[('note', 'Note'), ('photo', 'Photo'), ('event', 'Calendar event'), ('task', 'Task'), ('note_ref', 'Note reference'), ('shopping', 'Shopping item')], default='note', max_length=16),
        ),
        migrations.AddField(
            model_name='boardpost',
            name='target_id',
            field=models.UUIDField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='boardpost',
            name='position',
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(seed_pinboard, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='boardpost',
            options={'ordering': ['position', '-created_at', '-id']},
        ),
        migrations.RemoveIndex(model_name='boardpost', name='board_family_created'),
        migrations.AddIndex(model_name='boardpost', index=models.Index(fields=['family', 'position'], name='board_family_position')),
        migrations.AddIndex(model_name='boardpost', index=models.Index(fields=['family', '-created_at'], name='board_family_created')),
    ]
