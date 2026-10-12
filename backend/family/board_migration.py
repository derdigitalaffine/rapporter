"""Compatibility diagnostics for the legacy Board -> universal Pinboard cutover.

The important identity contract is deliberately simple: the original ``BoardPost``
row was expanded in place, so its UUID is also the canonical Pin UUID.  This
module never copies board content and never widens ACLs.  It only reports safe
counts and can repair the already-supported legacy ``kind`` -> ``adapter_key``
projection for rolling upgrades that still contain blank adapter keys.
"""

from collections import defaultdict

from django.db import transaction
from django.db.models import Count, F, Q

from .board_models import BoardImage, BoardPost
from .models import FamilyEvent, Routine, ShoppingItem, ShoppingList, Task
from .notes_models import Note
from .pin_adapters import LEGACY_KIND_TO_ADAPTER_KEY
from .travel_models import Trip


IDENTITY_STRATEGY = "boardpost_uuid_in_place"
NATIVE_KINDS = (BoardPost.Kind.NOTE, BoardPost.Kind.PHOTO)
REFERENCE_KINDS = tuple(LEGACY_KIND_TO_ADAPTER_KEY)


def repair_legacy_adapter_keys(*, batch_size=500):
    """Fill missing canonical adapter keys in bounded, retry-safe batches.

    The conditional update means concurrent/repeated runs can only change a row
    once.  Legacy ``kind`` and ``target_id`` remain untouched for rollback.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    migrated = 0
    while True:
        batch = list(
            BoardPost.objects.filter(
                kind__in=REFERENCE_KINDS,
                target_id__isnull=False,
                adapter_key="",
            )
            .order_by("id")
            .values_list("id", "kind")[:batch_size]
        )
        if not batch:
            return migrated

        by_kind = defaultdict(list)
        for post_id, kind in batch:
            by_kind[kind].append(post_id)

        changed = 0
        with transaction.atomic():
            for kind, post_ids in by_kind.items():
                changed += BoardPost.objects.filter(
                    id__in=post_ids,
                    kind=kind,
                    target_id__isnull=False,
                    adapter_key="",
                ).update(adapter_key=LEGACY_KIND_TO_ADAPTER_KEY[kind])
        migrated += changed
        if changed == 0:
            # A concurrent worker may have repaired the whole batch between the
            # read and update. Re-evaluate the queryset instead of spinning.
            continue


def _adapter_mismatch_query():
    query = Q(pk__in=[])
    for kind, adapter_key in LEGACY_KIND_TO_ADAPTER_KEY.items():
        query |= Q(kind=kind, target_id__isnull=False) & ~Q(adapter_key__in=("", adapter_key))
    return query


def _existing_reference_pairs(adapter_key, target_ids):
    """Return raw (family_id, target_id) pairs for count-only diagnostics.

    This intentionally does not use these raw querysets for authorization or API
    rendering.  Canonical PinAdapter/source ACL checks remain authoritative.
    """
    if adapter_key == "calendar_event":
        return set(FamilyEvent.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "task":
        return set(Task.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "note":
        return set(Note.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "shopping_item":
        return set(
            ShoppingItem.objects.filter(id__in=target_ids).values_list("shopping_list__family_id", "id")
        )
    if adapter_key == "routine":
        return set(Routine.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "shopping_list":
        return set(ShoppingList.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "trip":
        return set(Trip.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    if adapter_key == "document":
        from documents.models import Document

        return set(Document.objects.filter(id__in=target_ids).values_list("family_id", "id"))
    return set()


def count_orphaned_reference_pins():
    """Count reference pins whose target row no longer exists in that family."""
    grouped = defaultdict(list)
    for family_id, target_id, kind in BoardPost.objects.filter(
        kind__in=REFERENCE_KINDS,
        target_id__isnull=False,
    ).values_list("family_id", "target_id", "kind"):
        grouped[LEGACY_KIND_TO_ADAPTER_KEY[kind]].append((family_id, target_id))

    orphaned = 0
    for adapter_key, pairs in grouped.items():
        target_ids = {target_id for _, target_id in pairs}
        existing = _existing_reference_pairs(adapter_key, target_ids)
        orphaned += sum(1 for pair in pairs if pair not in existing)
    return orphaned


def migration_report(*, migrated=0, already_migrated=None):
    """Return migration health as counts only; never include user content."""
    total = BoardPost.objects.count()
    backfill_needed = BoardPost.objects.filter(
        kind__in=REFERENCE_KINDS,
        target_id__isnull=False,
        adapter_key="",
    ).count()
    adapter_mismatches = BoardPost.objects.filter(_adapter_mismatch_query()).count()
    reference_without_target = BoardPost.objects.filter(
        kind__in=REFERENCE_KINDS,
        target_id__isnull=True,
    ).count()
    native_identity_anomalies = BoardPost.objects.filter(
        Q(kind__in=NATIVE_KINDS) & (Q(target_id__isnull=False) | ~Q(adapter_key=""))
    ).count()

    selected_without_people = (
        BoardPost.objects.filter(visibility=BoardPost.Visibility.SELECTED)
        .annotate(member_count=Count("visible_to_memberships"))
        .filter(member_count=0)
        .count()
    )
    stale_non_selected_grants = (
        BoardPost.objects.exclude(visibility=BoardPost.Visibility.SELECTED)
        .filter(visible_to_memberships__isnull=False)
        .distinct()
        .count()
    )
    cross_family_grants = (
        BoardPost.objects.filter(visible_to_memberships__isnull=False)
        .exclude(family_id=F("visible_to_memberships__family_id"))
        .distinct()
        .count()
    )
    visibility_anomalies = selected_without_people + stale_non_selected_grants + cross_family_grants

    orphaned_images = BoardImage.objects.exclude(post_id__in=BoardPost.objects.values("id")).count()
    orphaned_targets = count_orphaned_reference_pins()
    errors = adapter_mismatches + reference_without_target + native_identity_anomalies
    if already_migrated is None:
        already_migrated = max(total - backfill_needed - errors, 0)

    return {
        "identity_strategy": IDENTITY_STRATEGY,
        "board_posts_total": total,
        "identity_compatible": total,
        "migrated": migrated,
        "already_migrated": already_migrated,
        "adapter_backfill_needed": backfill_needed,
        "adapter_mismatches": adapter_mismatches,
        "reference_without_target": reference_without_target,
        "native_identity_anomalies": native_identity_anomalies,
        "orphaned_images": orphaned_images,
        "orphaned_targets": orphaned_targets,
        "visibility_anomalies": visibility_anomalies,
        "errors": errors,
    }
