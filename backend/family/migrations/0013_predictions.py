import unicodedata
import uuid
from django.db import migrations, models
import django.db.models.deletion


def backfill_purchases(apps,schema_editor):
    ShoppingItem=apps.get_model('family','ShoppingItem');ShoppingPurchaseEvent=apps.get_model('family','ShoppingPurchaseEvent')
    for item in ShoppingItem.objects.filter(checked=True,checked_at__isnull=False).select_related('shopping_list'):
        name=(item.name or '').strip();normalized=unicodedata.normalize('NFKC',name).casefold()
        if normalized:ShoppingPurchaseEvent.objects.create(family_id=item.shopping_list.family_id,normalized_name=normalized,name=name,quantity=item.quantity,category=item.category,purchased_at=item.checked_at,source_item_id=item.id)


class Migration(migrations.Migration):
    dependencies=[('family','0012_family_messages')]
    operations=[
        migrations.CreateModel(name='ShoppingPurchaseEvent',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True)),('normalized_name',models.CharField(db_index=True,max_length=180)),('name',models.CharField(max_length=180)),('quantity',models.CharField(blank=True,max_length=40)),('category',models.CharField(blank=True,max_length=80)),('purchased_at',models.DateTimeField(db_index=True)),('source_item_id',models.UUIDField(blank=True,null=True)),('family',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='shopping_purchase_events',to='family.family'))],options={'ordering':['purchased_at']}),
        migrations.CreateModel(name='PredictionFeedback',fields=[('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),('created_at',models.DateTimeField(auto_now_add=True)),('updated_at',models.DateTimeField(auto_now=True)),('kind',models.CharField(choices=[('shopping','Shopping'),('routine','Routine')],max_length=16)),('subject_key',models.CharField(max_length=180)),('dismissed',models.BooleanField(default=False)),('snoozed_until',models.DateTimeField(blank=True,null=True)),('last_action',models.CharField(blank=True,max_length=24)),('family',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='prediction_feedback',to='family.family')),('membership',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='prediction_feedback',to='family.membership'))],options={'unique_together':{('membership','kind','subject_key')}}),
        migrations.AddIndex(model_name='shoppingpurchaseevent',index=models.Index(fields=['family','normalized_name','purchased_at'],name='fam_purchase_pattern_idx')),
        migrations.AddIndex(model_name='predictionfeedback',index=models.Index(fields=['family','kind'],name='fam_prediction_kind_idx')),
        migrations.RunPython(backfill_purchases,migrations.RunPython.noop),
    ]
