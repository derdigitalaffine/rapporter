from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from auth_identity.models import EmailIdentity
from auth_identity.service import (
    EmailConflictError,
    EmailIdentityError,
    create_primary_identity,
    set_primary_email_direct,
)
from telemetry.service import try_record_audit_event

from .superadmin_user_views import (
    USER_DEFAULT_PAGE_SIZE,
    USER_MAX_PAGE_SIZE,
    USER_SORTS,
    _parse_positive_int,
    _target_user,
    _user_detail_payload,
    _user_row,
    _users_queryset,
)
from .superadmin_views import IsSuperAdmin, _enforce_sensitive_action, _rate_limited_response


def _row(user):
    payload = _user_row(user)
    payload.update({"first_name": user.first_name, "last_name": user.last_name})
    return payload


def _error(detail, *, code, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": detail, "code": code}, status=http_status)


def _sensitive_guard(request):
    try:
        decision = _enforce_sensitive_action(request)
    except Exception:
        raise
    if not decision.allowed:
        return _rate_limited_response(decision)
    return None


def _normalized_username(value):
    return str(value or "").strip()


def _username_conflict(username, *, exclude_pk=None):
    query = get_user_model().objects.filter(username__iexact=username)
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    return query.exists()


def _validate_password(value, *, user=None, required=False):
    password = str(value or "")
    if not password:
        if required:
            return None, _error("Passwort ist erforderlich.", code="password_required")
        return "", None
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return None, Response(
            {"detail": "Passwort erfüllt die Sicherheitsanforderungen nicht.", "code": "invalid_password", "errors": list(exc.messages)},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return password, None


def _active_superadmin_would_remain(target):
    return get_user_model().objects.filter(is_superuser=True, is_active=True).exclude(pk=target.pk).exists()


def _would_remove_last_active_superadmin(target, *, next_active=None, next_superuser=None):
    if not target.is_superuser or not target.is_active:
        return False
    resulting_active = target.is_active if next_active is None else bool(next_active)
    resulting_superuser = target.is_superuser if next_superuser is None else bool(next_superuser)
    if resulting_active and resulting_superuser:
        return False
    return not _active_superadmin_would_remain(target)


def _audit(event_key, request, target_id):
    try_record_audit_event(
        event_key,
        actor=request.user,
        actor_class="superadmin",
        target_type="user",
        target_id=str(target_id),
    )


def _list_users(request):
    query = str(request.query_params.get("q") or "").strip()
    account_status = str(request.query_params.get("status") or "").strip().lower()
    sort = str(request.query_params.get("sort") or "-last_activity").strip()
    if sort not in USER_SORTS:
        return _error("Unsupported user sort.", code="invalid_sort")

    limit = _parse_positive_int(request.query_params.get("limit"), USER_DEFAULT_PAGE_SIZE)
    offset = _parse_positive_int(request.query_params.get("offset"), 0, allow_zero=True)
    if limit is None or limit > USER_MAX_PAGE_SIZE or offset is None:
        return _error("Invalid pagination.", code="invalid_pagination")

    queryset = _users_queryset()
    if query:
        filters = Q(username__icontains=query) | Q(email__icontains=query)
        if query.isdigit():
            filters |= Q(pk=int(query))
        queryset = queryset.filter(filters)
    if account_status == "active":
        queryset = queryset.filter(is_active=True)
    elif account_status == "inactive":
        queryset = queryset.filter(is_active=False)
    elif account_status:
        return _error("Unsupported user status.", code="invalid_status")

    queryset = queryset.order_by(*USER_SORTS[sort]).distinct()
    count = queryset.count()
    users = list(queryset[offset : offset + limit])
    return Response({"count": count, "limit": limit, "offset": offset, "results": [_row(user) for user in users]})


def _create_user(request):
    guard = _sensitive_guard(request)
    if guard:
        return guard

    username = _normalized_username(request.data.get("username"))
    if not username:
        return _error("Benutzername ist erforderlich.", code="username_required")
    if _username_conflict(username):
        return _error("Benutzername ist bereits vergeben.", code="username_conflict", http_status=status.HTTP_409_CONFLICT)

    password, password_error = _validate_password(request.data.get("password"), required=True)
    if password_error:
        return password_error

    email_supplied = "email" in request.data
    email = str(request.data.get("email") or "").strip()
    is_active = bool(request.data.get("is_active", True))
    is_superuser = bool(request.data.get("is_superuser", False))
    first_name = str(request.data.get("first_name") or "").strip()
    last_name = str(request.data.get("last_name") or "").strip()
    User = get_user_model()

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                email="",
                password=password,
                first_name=first_name,
                last_name=last_name,
                is_active=is_active,
                is_superuser=is_superuser,
                is_staff=is_superuser,
            )
            if email_supplied and email:
                create_primary_identity(user, email, verified=True)
            _audit("superadmin.user.created", request, user.pk)
    except (EmailConflictError, EmailIdentityError):
        return _error("E-Mail-Adresse ist ungültig oder bereits vergeben.", code="email_conflict", http_status=status.HTTP_409_CONFLICT)
    except IntegrityError:
        return _error("Benutzer konnte wegen eines Datenkonflikts nicht angelegt werden.", code="user_conflict", http_status=status.HTTP_409_CONFLICT)

    user = _users_queryset().get(pk=user.pk)
    return Response({"user": _row(user)}, status=status.HTTP_201_CREATED)


def _update_user(request, target):
    guard = _sensitive_guard(request)
    if guard:
        return guard

    data = request.data
    username = _normalized_username(data.get("username", target.username))
    if not username:
        return _error("Benutzername ist erforderlich.", code="username_required")
    if _username_conflict(username, exclude_pk=target.pk):
        return _error("Benutzername ist bereits vergeben.", code="username_conflict", http_status=status.HTTP_409_CONFLICT)

    next_active = bool(data.get("is_active", target.is_active))
    next_superuser = bool(data.get("is_superuser", target.is_superuser))
    if target.pk == request.user.pk and (not next_active or not next_superuser):
        return _error(
            "Der aktuell angemeldete Superadmin kann sich nicht selbst deaktivieren oder herabstufen.",
            code="self_protection",
            http_status=status.HTTP_409_CONFLICT,
        )
    if _would_remove_last_active_superadmin(target, next_active=next_active, next_superuser=next_superuser):
        return _error(
            "Mindestens ein aktiver Superadmin muss erhalten bleiben.",
            code="last_active_superadmin",
            http_status=status.HTTP_409_CONFLICT,
        )

    password, password_error = _validate_password(data.get("password"), user=target, required=False)
    if password_error:
        return password_error

    was_active = target.is_active
    was_superuser = target.is_superuser
    email_changed = False
    try:
        with transaction.atomic():
            locked = get_user_model().objects.select_for_update().get(pk=target.pk)
            locked.username = username
            locked.first_name = str(data.get("first_name", locked.first_name) or "").strip()
            locked.last_name = str(data.get("last_name", locked.last_name) or "").strip()
            locked.is_active = next_active
            locked.is_superuser = next_superuser
            locked.is_staff = next_superuser
            if password:
                locked.set_password(password)
            locked.save()

            if "email" in data:
                email = str(data.get("email") or "").strip()
                if email:
                    set_primary_email_direct(locked, email)
                else:
                    EmailIdentity.objects.filter(user=locked).delete()
                    if locked.email:
                        locked.email = ""
                        locked.save(update_fields=["email"])
                email_changed = True

            if was_active != next_active:
                _audit("superadmin.user.reactivated" if next_active else "superadmin.user.deactivated", request, locked.pk)
            if was_superuser != next_superuser or username != target.username or password or email_changed or locked.first_name != target.first_name or locked.last_name != target.last_name:
                _audit("superadmin.user.updated", request, locked.pk)
    except (EmailConflictError, EmailIdentityError):
        return _error("E-Mail-Adresse ist ungültig oder bereits vergeben.", code="email_conflict", http_status=status.HTTP_409_CONFLICT)
    except IntegrityError:
        return _error("Benutzer konnte wegen eines Datenkonflikts nicht gespeichert werden.", code="user_conflict", http_status=status.HTTP_409_CONFLICT)

    updated = _users_queryset().get(pk=target.pk)
    return Response({"user": _row(updated)})


def _delete_user(request, target):
    guard = _sensitive_guard(request)
    if guard:
        return guard
    if target.pk == request.user.pk:
        return _error("Der aktuell angemeldete Superadmin kann sich nicht selbst löschen.", code="self_protection", http_status=status.HTTP_409_CONFLICT)
    if target.is_superuser and target.is_active and not _active_superadmin_would_remain(target):
        return _error("Mindestens ein aktiver Superadmin muss erhalten bleiben.", code="last_active_superadmin", http_status=status.HTTP_409_CONFLICT)

    confirmed = request.data.get("confirm") is True
    typed_username = str(request.data.get("confirm_username") or "")
    if not confirmed or typed_username != target.username:
        return _error(
            "Dauerhaftes Löschen erfordert Bestätigung und den exakten Benutzernamen.",
            code="double_confirmation_required",
            http_status=status.HTTP_409_CONFLICT,
        )

    target_id = target.pk
    target_username = target.username
    with transaction.atomic():
        locked = get_user_model().objects.select_for_update().get(pk=target_id)
        if locked.username != target_username:
            return _error("Benutzerdaten haben sich geändert. Bitte Löschung erneut bestätigen.", code="confirmation_stale", http_status=status.HTTP_409_CONFLICT)
        deleted_count, deleted_by_model = locked.delete()
        _audit("superadmin.user.purged", request, target_id)

    return Response(
        {
            "deleted": True,
            "user_id": target_id,
            "deleted_rows": deleted_count,
            "deleted_by_model": deleted_by_model,
        }
    )


@api_view(["GET", "POST"])
@permission_classes([IsSuperAdmin])
def superadmin_users_crud(request):
    if request.method == "GET":
        return _list_users(request)
    return _create_user(request)


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsSuperAdmin])
def superadmin_user_crud_detail(request, user_id):
    target = _target_user(user_id)
    if target is None:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
    if request.method == "GET":
        return Response(_user_detail_payload(target))
    if request.method == "PATCH":
        return _update_user(request, target)
    return _delete_user(request, target)
