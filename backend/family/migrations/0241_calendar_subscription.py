import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('family', '0240_offline_sync_foundation'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='CalendarSubscription',
        fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('created_at', models.DateTimeField(auto_now_add=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('name', models.CharField(max_length=80)),
            ('token_digest', models.CharField(max_length=64, unique=True)),
            ('credentials_encrypted', models.TextField()),
            ('revoked_at', models.DateTimeField(null=True, blank=True)),
            ('last_used_at', models.DateTimeField(null=True, blank=True)),
            ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_subscriptions', to=settings.AUTH_USER_MODEL)),
            ('family', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='calendar_subscriptions', to='family.family')),
        ], options={'ordering': ['-created_at']},
    )]
