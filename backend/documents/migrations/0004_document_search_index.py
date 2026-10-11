from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import migrations, models
import django.db.models.deletion


SEARCHABLE_FIELD_KEYS = {
    "reference",
    "reference_number",
    "case_number",
    "aktenzeichen",
    "document.reference",
    "letter.reference",
    "contract.number",
    "contract.provider",
    "contract.start_date",
    "contract.end_date",
    "receipt.merchant",
    "receipt.total",
    "receipt.date",
    "iban",
    "bank.iban",
}


def _value_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        if "value" in value:
            return _value_text(value.get("value"))
        return " ".join(_value_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_value_text(item) for item in value)
    return str(value)


def backfill_search_content(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    Run = apps.get_model("documents", "DocumentProcessingRun")
    Field = apps.get_model("documents", "ExtractedField")
    SearchIndex = apps.get_model("documents", "DocumentSearchIndex")
    batch = []
    for document in Document.objects.filter(library_visible=True).iterator(chunk_size=200):
        parts = [document.title, document.correspondent, document.kind]
        run = (
            Run.objects.filter(document_id=document.pk)
            .exclude(normalized_text="")
            .order_by("-processed_at", "-created_at")
            .first()
        )
        if run:
            parts.append(run.normalized_text)
            values = Field.objects.filter(
                processing_run_id=run.pk,
                key__in=SEARCHABLE_FIELD_KEYS,
            ).values_list("value_json", flat=True)
            parts.extend(_value_text(value)[:2000] for value in values)
        content = "\n".join(str(part).strip() for part in parts if str(part or "").strip())
        batch.append(SearchIndex(document_id=document.pk, content=content))
        if len(batch) >= 200:
            SearchIndex.objects.bulk_create(batch, ignore_conflicts=True)
            batch = []
    if batch:
        SearchIndex.objects.bulk_create(batch, ignore_conflicts=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("documents", "0003_document_library_visible")]

    operations = [
        migrations.CreateModel(
            name="DocumentSearchIndex",
            fields=[
                (
                    "document",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="search_index",
                        serialize=False,
                        to="documents.document",
                    ),
                ),
                ("content", models.TextField(blank=True)),
                ("search_vector", SearchVectorField(null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "indexes": [GinIndex(fields=["search_vector"], name="doc_search_vector_gin")],
            },
        ),
        migrations.RunPython(backfill_search_content, noop_reverse),
        migrations.RunSQL(
            "UPDATE documents_documentsearchindex SET search_vector = to_tsvector('simple', coalesce(content, ''))",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
