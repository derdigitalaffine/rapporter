import csv
import html
import io
from collections import Counter
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from .care_service import _baby_for_user as care_baby_for_user, care_summary
from .development_service import development_payload
from .growth_service import growth_payload
from .models import BabyCareLog, DevelopmentObservation, ReportExportAudit


ALLOWED_SECTIONS = {"care", "growth", "development", "handover"}


def _range(start=None, end=None):
    end = end or timezone.now()
    start = start or (end - timedelta(days=7))
    if start >= end:
        raise ValidationError({"range": "Report start must be before report end."})
    if end - start > timedelta(days=366):
        raise ValidationError({"range": "Reports are limited to 366 days per export."})
    return start, end


def report_payload(user, baby_id, *, start=None, end=None, sections=None, language="de"):
    baby, membership, access = care_baby_for_user(user, baby_id, "report")
    start, end = _range(start, end)
    selected = set(sections or ALLOWED_SECTIONS)
    unknown = selected - ALLOWED_SECTIONS
    if unknown:
        raise ValidationError({"sections": f"Unknown report sections: {', '.join(sorted(unknown))}"})
    if selected & {"care", "handover"} and not access.can_log_care:
        raise PermissionDenied("Care and handover sections are not permitted for this Care Circle member.")
    if selected & {"growth", "development"} and not access.can_view_growth_development:
        raise PermissionDenied("Growth and development sections are not permitted for this Care Circle member.")
    payload = {
        "baby": {"id": str(baby.id), "display_name": baby.display_name, "birth_date": baby.birth_date.isoformat()},
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "sections": sorted(selected),
        "notice": "This report summarizes recorded observations and care events. It does not provide a diagnosis.",
    }
    if "care" in selected:
        rows = list(BabyCareLog.objects.filter(baby=baby, started_at__gte=start, started_at__lte=end).order_by("started_at"))
        counts = Counter(row.kind for row in rows)
        payload["care"] = {
            "counts": dict(counts),
            "events": [
                {
                    "id": str(row.id),
                    "kind": row.kind,
                    "started_at": row.started_at.isoformat(),
                    "ended_at": row.ended_at.isoformat() if row.ended_at else None,
                    "value": row.value,
                }
                for row in rows
            ],
        }
    if "growth" in selected:
        growth_data = growth_payload(user, baby.id)
        growth_data["points"] = [point for point in growth_data["points"] if start <= datetime.fromisoformat(point["measured_at"]) <= end]
        payload["growth"] = growth_data
    if "development" in selected:
        observations = DevelopmentObservation.objects.filter(baby=baby).filter(
            Q(observed_at__gte=start, observed_at__lte=end)
            | Q(observed_at__isnull=True, created_at__gte=start, created_at__lte=end)
        ).order_by("created_at")
        payload["development"] = {
            "current_checklist": development_payload(user, baby.id, language=language),
            "observations": [
                {
                    "id": str(row.id),
                    "milestone_key": row.milestone_key,
                    "title": row.title,
                    "state": row.state,
                    "observed_at": row.observed_at.isoformat() if row.observed_at else None,
                    "note": row.note,
                }
                for row in observations
            ],
        }
    if "handover" in selected:
        payload["handover"] = {
            "summary_24h": care_summary(user, baby.id, hours=24),
            "notes": [
                {
                    "id": str(row.id),
                    "from_at": row.from_at.isoformat(),
                    "to_at": row.to_at.isoformat(),
                    "note": row.note,
                }
                for row in baby.handover_notes.filter(to_at__gte=start, from_at__lte=end).order_by("from_at")
            ],
        }
    return baby, membership, payload


def _flatten(prefix, value, rows):
    if isinstance(value, dict):
        for key, nested in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), nested, rows)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _flatten(f"{prefix}[{index}]", nested, rows)
    else:
        rows.append((prefix, "" if value is None else value))


def export_csv(payload):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["field", "value"])
    rows = []
    _flatten("", payload, rows)
    writer.writerows(rows)
    return output.getvalue()


def export_html(payload):
    title = f"FamilyOS · {payload['baby']['display_name']}"
    blocks = []
    for section in payload["sections"]:
        data = payload.get(section)
        if data is None:
            continue
        rows = []
        _flatten(section, data, rows)
        table = "".join(f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>" for key, value in rows)
        blocks.append(f"<section><h2>{html.escape(section.title())}</h2><table>{table}</table></section>")
    return f"""<!doctype html><html lang=\"de\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title><style>body{{font:15px system-ui;margin:32px;color:#173c43}}h1,h2{{margin:.5em 0}}table{{border-collapse:collapse;width:100%;margin-bottom:24px}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #e7ebe5;padding:8px}}th{{width:32%}}.notice{{padding:12px;background:#f7f8f3;border-radius:10px}}@media print{{body{{margin:12mm}}}}</style></head><body><h1>{html.escape(title)}</h1><p>{html.escape(payload['range']['start'])} – {html.escape(payload['range']['end'])}</p><p class=\"notice\">{html.escape(payload['notice'])}</p>{''.join(blocks)}</body></html>"""


def audited_export(user, baby_id, *, export_format="json", start=None, end=None, sections=None, language="de"):
    baby, membership, payload = report_payload(user, baby_id, start=start, end=end, sections=sections, language=language)
    if export_format not in {"json", "csv", "html"}:
        raise ValidationError({"format": "Use json, csv or html."})
    start_dt = datetime.fromisoformat(payload["range"]["start"])
    end_dt = datetime.fromisoformat(payload["range"]["end"])
    ReportExportAudit.objects.create(
        baby=baby,
        membership=membership,
        export_format=export_format,
        sections=payload["sections"],
        range_start=start_dt,
        range_end=end_dt,
    )
    if export_format == "csv":
        return payload, export_csv(payload), "text/csv; charset=utf-8"
    if export_format == "html":
        return payload, export_html(payload), "text/html; charset=utf-8"
    return payload, payload, "application/json"
