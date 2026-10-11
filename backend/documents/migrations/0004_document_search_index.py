import re

import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
from django.db import migrations, models


SEARCHABLE_KEYS = {
    "reference_number",
    "document_number",
    "invoice_number",
    "contract_number",
    "customer_number",
    "policy_number",
    "claim_number",
    "order_number",
    "tracking_number",
    "merchant",
    "provider",
    "issuer",
    "recipient",
    "subject",
}


def _flatten(value):
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, (str, int, float)):
        return [str(value)]
    if isinstance(value, dict):
        result = []
        for nested in value.values():
            result.extend(_flatten(nested))
        return result
    if isinstance(value, (list, tuple)):
        result = []
        for nested in value:
            result.extend(_flatten(nested))
        return result
    return []


def _normalized(parts):
    values = []
    for part in parts:
        cleaned = re.sub(r"\s+", " ", str(part or "")).strip()
        if cleaned:
            values.append(cleaned)
    return "\n".join(values)


def backfill_search_index(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    ProcessingRun = apps.get_model("documents", "DocumentProcessingRun")
    ExtractedField = apps.get_model("documents", "ExtractedField")
    SearchIndex = apps.get_model("documents", "DocumentSearchIndex")

    rows = []
    for document in Document.objects.all().iterator(chunk_size=200):
        run = (
            ProcessingRun.objects.filter(document_id=document.pk, status__in=["review", "ready"])
            .order_by("-processed_at", "-created_at")
            .first()
        )
        parts = [document.title, document.correspondent, document.kind]
        if run:
            parts.append(run.normalized_text)
            for value in ExtractedField.objects.filter(
                processing_run_id=run.pk,
                key__in=SEARCHABLE_KEYS,
            ).values_list("value_json", flat=True):
                parts.extend(_flatten(value))
        rows.append(
            SearchIndex(
                document_id=document.pk,
                search_text=_normalized(parts),
                indexed_processing_run_id=run.pk if run else None,
            )
        )
        if len(rows) >= 200:
            SearchIndex.objects.bulk_create(rows)
            rows = []
    if rows:
        SearchIndex.objects.bulk_create(rows)

    table = schema_editor.connection.ops.quote_name(SearchIndex._meta.db_table)
    schema_editor.execute(
        f"UPDATE {table} SET search_vector = to_tsvector('simple', COALESCE(search_text, ''))"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0003_document_library_visible"),
    ]

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
                ("search_text", models.TextField(blank=True, default="")),
                ("search_vector", django.contrib.postgres.search.SearchVectorField(null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "indexed_processing_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="documents.documentprocessingrun",
                    ),
                ),
            ],
            options={
                "indexes": [
                    django.contrib.postgres.indexes.GinIndex(
                        fields=["search_vector"],
                        name="doc_search_vector_gin",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_search_index, migrations.RunPython.noop),
    ]
