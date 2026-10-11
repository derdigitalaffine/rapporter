from django.db import migrations, models


LEGACY_KIND_TO_ADAPTER_KEY = {
    'event': 'calendar_event',
    'task': 'task',
    'note_ref': 'note',
    'shopping': 'shopping_item',
    'routine': 'routine',
    'shopping_list': 'shopping_list',
    'trip': 'trip',
    'document': 'document',
}


def backfill_pin_adapter_keys(apps, schema_editor):
    BoardPost = apps.get_model('family', 'BoardPost')
    for legacy_kind, adapter_key in LEGACY_KIND_TO_ADAPTER_KEY.items():
        BoardPost.objects.filter(
            kind=legacy_kind,
            target_id__isnull=False,
            adapter_key='',
        ).update(adapter_key=adapter_key)


def clear_pin_adapter_keys(apps, schema_editor):
    BoardPost = apps.get_model('family', 'BoardPost')
    BoardPost.objects.exclude(adapter_key='').update(adapter_key='')


class Migration(migrations.Migration):
    dependencies = [
        ('family', '0219_todo_preferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='boardpost',
            name='adapter_key',
            field=models.CharField(blank=True, db_index=True, default='', max_length=32),
            preserve_default=False,
        ),
        migrations.RunPython(backfill_pin_adapter_keys, clear_pin_adapter_keys),
    ]
