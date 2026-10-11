from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from family.context_links import ContextLinkError, create_context_link

from .access import (
    active_membership,
    can_create_wishlist,
    can_manage_wishlist,
    can_view_item,
    can_view_wishlist,
    visible_wishlists,
)
from .models import Wishlist, WishlistItem
from .serializers import item_payload, wishlist_payload
from .services import (
    ProjectionConflict,
    ReservationConflict,
    apply_item_fields,
    clear_reservation,
    create_follow_up,
    prepare_access,
    replace_access,
    set_reservation,
)


def _wishlist_queryset():
    return Wishlist.objects.select_related(
        "family",
        "owner_membership",
        "owner_membership__user",
    ).prefetch_related(
        "access_entries",
        "access_entries__membership",
        "access_entries__membership__user",
        "items",
        "items__wishlist",
        "items__wishlist__owner_membership",
        "items__reservation",
        "items__reservation__reserved_by",
        "items__reservation__reserved_by__user",
    )


def _wishlist_or_404(user, wishlist_id, *, manage=False):
    wishlist = _wishlist_queryset().filter(id=wishlist_id).first()
    if not wishlist:
        raise Http404
    allowed = can_manage_wishlist(user, wishlist) if manage else can_view_wishlist(user, wishlist)
    if not allowed:
        raise Http404
    return wishlist


def _item_or_404(user, item_id, *, manage=False):
    item = (
        WishlistItem.objects.select_related(
            "wishlist",
            "wishlist__family",
            "wishlist__owner_membership",
            "wishlist__owner_membership__user",
        )
        .prefetch_related("reservation", "reservation__reserved_by", "reservation__reserved_by__user")
        .filter(id=item_id, archived_at__isnull=True)
        .first()
    )
    if not item:
        raise Http404
    allowed = can_manage_wishlist(user, item.wishlist) if manage else can_view_item(user, item)
    if not allowed:
        raise Http404
    return item


def _valid_visibility(value):
    visibility = str(value or Wishlist.Visibility.SELECTED)
    if visibility not in {choice for choice, _ in Wishlist.Visibility.choices}:
        raise ValidationError({"visibility": "Ungültige Sichtbarkeit."})
    return visibility


def _access_rows(family_id, raw):
    try:
        return prepare_access(family_id, raw)
    except ValueError:
        raise ValidationError({"access": "Mindestens eine gültige Mitgliedschaft dieser Familie erwartet."}) from None


def _item_validation_error(code):
    mapping = {
        "title_required": {"title": "Name fehlt."},
        "invalid_https_url": {"url": "Nur normale HTTPS-Links ohne eingebettete Zugangsdaten sind erlaubt."},
        "invalid_priority": {"priority": "Ungültige Priorität."},
    }
    raise ValidationError(mapping.get(code, {"detail": "Ungültige Eingabe."}))


@api_view(["GET", "POST"])
def wishlist_collection(request):
    family_id = request.query_params.get("family") if request.method == "GET" else request.data.get("family")
    membership = active_membership(request.user, family_id)
    if not membership:
        raise Http404

    if request.method == "GET":
        rows = (
            visible_wishlists(request.user, family_id)
            .select_related("owner_membership", "owner_membership__user")
            .prefetch_related(
                "access_entries__membership__user",
                "items__reservation__reserved_by__user",
            )
        )
        return Response([wishlist_payload(row, request.user) for row in rows])

    if not can_create_wishlist(request.user, family_id):
        raise Http404
    title = str(request.data.get("title") or "").strip()
    if not title:
        raise ValidationError({"title": "Titel fehlt."})
    access = _access_rows(family_id, request.data.get("access"))
    with transaction.atomic():
        wishlist = Wishlist.objects.create(
            family_id=family_id,
            owner_membership=membership,
            title=title[:160],
            visibility=_valid_visibility(request.data.get("visibility")),
            created_by=request.user,
        )
        replace_access(wishlist, access)
    return Response(wishlist_payload(_wishlist_or_404(request.user, wishlist.id, manage=True), request.user), status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH", "DELETE"])
def wishlist_detail(request, wishlist_id):
    wishlist = _wishlist_or_404(request.user, wishlist_id, manage=request.method != "GET")
    if request.method == "GET":
        return Response(wishlist_payload(wishlist, request.user))
    if request.method == "DELETE":
        wishlist.active = False
        wishlist.save(update_fields=["active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    updates = []
    if "title" in request.data:
        title = str(request.data.get("title") or "").strip()
        if not title:
            raise ValidationError({"title": "Titel fehlt."})
        wishlist.title = title[:160]
        updates.append("title")
    if "visibility" in request.data:
        wishlist.visibility = _valid_visibility(request.data.get("visibility"))
        updates.append("visibility")
    if "active" in request.data:
        wishlist.active = bool(request.data.get("active"))
        updates.append("active")
    access = _access_rows(wishlist.family_id, request.data.get("access")) if "access" in request.data else None
    with transaction.atomic():
        if updates:
            wishlist.save(update_fields=[*updates, "updated_at"])
        if access is not None:
            replace_access(wishlist, access)
    return Response(wishlist_payload(_wishlist_or_404(request.user, wishlist.id, manage=True), request.user))


@api_view(["POST"])
def wishlist_item_collection(request, wishlist_id):
    wishlist = _wishlist_or_404(request.user, wishlist_id, manage=True)
    item = WishlistItem(wishlist=wishlist, created_by=request.user)
    try:
        apply_item_fields(item, request.data)
        if not item.title:
            raise ValueError("title_required")
    except ValueError as exc:
        _item_validation_error(str(exc))
    item.save()
    return Response(item_payload(item, request.user), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
def wishlist_item_detail(request, item_id):
    item = _item_or_404(request.user, item_id, manage=True)
    if request.method == "DELETE":
        item.archived_at = timezone.now()
        item.save(update_fields=["archived_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
    try:
        updates = apply_item_fields(item, request.data)
    except ValueError as exc:
        _item_validation_error(str(exc))
    if updates:
        item.save(update_fields=[*updates, "updated_at"])
    return Response(item_payload(item, request.user))


@api_view(["POST", "DELETE"])
def wishlist_reservation(request, item_id):
    # Owner-facing reads never expose reservation existence, and the owner also
    # receives the same neutral unavailable response on this mutation endpoint.
    item = _item_or_404(request.user, item_id)
    if can_manage_wishlist(request.user, item.wishlist):
        raise Http404
    try:
        if request.method == "DELETE":
            item = clear_reservation(user=request.user, item_id=item.id)
        else:
            reservation_status = str(request.data.get("status") or "reserved")
            item, _ = set_reservation(
                user=request.user,
                item_id=item.id,
                status=reservation_status,
                note=request.data.get("note", ""),
            )
    except PermissionError:
        raise Http404
    except ReservationConflict:
        return Response(
            {"code": "already_reserved", "detail": "Dieser Wunsch ist bereits von einer anderen Person reserviert."},
            status=status.HTTP_409_CONFLICT,
        )
    except ValueError:
        raise ValidationError({"status": "Ungültiger Reservierungsstatus."}) from None
    return Response(item_payload(_item_or_404(request.user, item.id), request.user))


@api_view(["POST"])
def wishlist_action(request, item_id):
    item = _item_or_404(request.user, item_id)
    if request.data.get("confirmed") is not True:
        raise ValidationError({"confirmed": "Folgeaktionen benötigen eine ausdrückliche Bestätigung."})
    action = str(request.data.get("action") or "")
    try:
        kind, created = create_follow_up(user=request.user, item=item, action=action, payload=request.data)
    except PermissionError:
        raise Http404
    except ProjectionConflict as exc:
        code = str(exc)
        detail = {
            "selected_wishlist_action": "Nur familienweit sichtbare Wunschlisten dürfen in familienweite Folgeobjekte projiziert werden.",
            "expense_family_visibility": "Ausgaben sind aktuell familienweit sichtbar. Diese Sichtbarkeit muss separat bestätigt werden.",
        }.get(code, "Aktion ist mit der aktuellen Sichtbarkeit nicht erlaubt.")
        return Response({"code": code, "detail": detail}, status=status.HTTP_409_CONFLICT)
    except ValueError as exc:
        code = str(exc)
        details = {
            "shopping_list_required": "Gültige Einkaufsliste erforderlich.",
            "invalid_amount": "Für eine Ausgabe ist ein positiver Betrag erforderlich.",
            "invalid_currency": "Ungültige Währung.",
            "title_required": "Titel fehlt.",
            "unknown_action": "Unbekannte Aktion.",
        }
        raise ValidationError({"code": code, "detail": details.get(code, "Ungültige Eingabe.")}) from None
    return Response({"kind": kind, "id": str(created.id)}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def wishlist_context(request, wishlist_id):
    wishlist = _wishlist_or_404(request.user, wishlist_id, manage=True)
    if request.data.get("confirmed") is not True:
        raise ValidationError({"confirmed": "Verknüpfungen benötigen eine ausdrückliche Bestätigung."})
    context_type = str(request.data.get("context_type") or "")
    context_id = request.data.get("context_id")
    relation_key = str(request.data.get("relation_key") or "birthday.wishlist")
    try:
        link, created = create_context_link(
            user=request.user,
            family=wishlist.family,
            source_type="wishlist",
            source_id=wishlist.id,
            context_type=context_type,
            context_id=context_id,
            relation_key=relation_key,
        )
    except ContextLinkError:
        raise Http404
    return Response({"id": str(link.id), "created": created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
