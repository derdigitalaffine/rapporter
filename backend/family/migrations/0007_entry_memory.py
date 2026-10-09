from collections import defaultdict
import unicodedata

from django.db import migrations, models
from django.utils import timezone
import django.db.models.deletion
import uuid


def normalize(value):
    return unicodedata.normalize("NFKC", value or "").strip().casefold()


def backfill(apps, schema_editor):
    EntryMemory = apps.get_model("family", "EntryMemory")
    Task = apps.get_model("family", "Task")
    ShoppingItem = apps.get_model("family", "ShoppingItem")
    grouped = {}
    for task in Task.objects.select_related("family").all().order_by("created_at"):
        key=(task.family_id,"task",normalize(task.title))
        if not key[2]: continue
        row=grouped.setdefault(key,{"name":task.title,"count":0,"last":task.updated_at or task.created_at,"data":{}})
        row["count"]+=1; row["name"]=task.title; row["last"]=max(row["last"],task.updated_at or task.created_at)
        row["data"]={"notes":task.notes,"priority":task.priority,"estimate_minutes":task.estimate_minutes,"recurrence":task.recurrence,"tags":task.tags or []}
    for item in ShoppingItem.objects.select_related("shopping_list").all().order_by("created_at"):
        key=(item.shopping_list.family_id,"shopping",normalize(item.name))
        if not key[2]: continue
        row=grouped.setdefault(key,{"name":item.name,"count":0,"last":item.updated_at or item.created_at,"data":{}})
        row["count"]+=1; row["name"]=item.name; row["last"]=max(row["last"],item.updated_at or item.created_at)
        row["data"]={"quantity":item.quantity,"category":item.category,"aisle":item.aisle,"note":item.note,"favorite":item.favorite}
    for (family_id,kind,normalized), row in grouped.items():
        EntryMemory.objects.create(family_id=family_id,kind=kind,normalized_name=normalized,name=row["name"],data=row["data"],use_count=row["count"],last_used_at=row["last"] or timezone.now())


class Migration(migrations.Migration):
    dependencies=[("family","0006_push_subscriptions")]
    operations=[
        migrations.CreateModel(
            name="EntryMemory",
            fields=[
                ("id",models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),
                ("created_at",models.DateTimeField(auto_now_add=True)),
                ("updated_at",models.DateTimeField(auto_now=True)),
                ("kind",models.CharField(choices=[("task","Task"),("shopping","Shopping")],max_length=16)),
                ("normalized_name",models.CharField(max_length=180)),
                ("name",models.CharField(max_length=180)),
                ("data",models.JSONField(blank=True,default=dict)),
                ("use_count",models.PositiveIntegerField(default=1)),
                ("last_used_at",models.DateTimeField()),
                ("family",models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name="entry_memories",to="family.family")),
            ],
            options={"unique_together":{("family","kind","normalized_name")}},
        ),
        migrations.AddIndex(model_name="entrymemory",index=models.Index(fields=["family","kind","last_used_at"],name="fam_mem_family_kind_idx")),
        migrations.RunPython(backfill,migrations.RunPython.noop),
    ]
