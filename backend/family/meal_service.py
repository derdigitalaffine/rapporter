from collections import OrderedDict
from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from .meal_models import MealPlanEntry, MealShoppingTransfer, MealShoppingTransferItem
from .memory import normalize_name
from .models import Family, ShoppingItem, ShoppingList
from .shopping_access import can_access_shopping_list


def family_for_user(user, family_id):
    family = Family.objects.filter(id=family_id, memberships__user=user).first()
    if not family:
        raise PermissionDenied("Familie nicht gefunden oder nicht freigegeben.")
    return family


def shopping_list_for_user(user, family, shopping_list_id):
    shopping_list = ShoppingList.objects.filter(id=shopping_list_id, family=family, archived=False).first()
    if not shopping_list or not can_access_shopping_list(user, shopping_list):
        raise PermissionDenied("Einkaufsliste nicht gefunden oder nicht freigegeben.")
    return shopping_list


def _decimal_text(value):
    if value is None:
        return ""
    value = value.quantize(Decimal("0.001"))
    text = format(value, "f").rstrip("0").rstrip(".")
    return text or "0"


def _quantity_text(quantity, unit):
    number = _decimal_text(quantity)
    if number and unit:
        return f"{number} {unit}"[:40]
    return (number or "")[:40]


def aggregate_meal_demand(family, start_date, end_date):
    entries = (
        MealPlanEntry.objects.filter(
            family=family,
            date__gte=start_date,
            date__lte=end_date,
            dish__isnull=False,
        )
        .select_related("dish")
        .prefetch_related("dish__ingredients")
        .order_by("date", "slot", "id")
    )
    rows = OrderedDict()
    for entry in entries:
        servings = Decimal(entry.servings or entry.dish.default_servings or 1)
        default_servings = Decimal(entry.dish.default_servings or 1)
        scale = servings / default_servings
        for ingredient in entry.dish.ingredients.all():
            normalized = normalize_name(ingredient.name) or ingredient.name.strip().casefold()
            unit = ingredient.unit.strip()
            quantified = ingredient.quantity is not None
            key = f"{normalized}|{unit.casefold()}|{'q' if quantified else 'u'}"
            quantity = ingredient.quantity * scale if quantified else None
            if key not in rows:
                rows[key] = {
                    "key": key,
                    "name": ingredient.name.strip(),
                    "quantity": quantity,
                    "unit": unit,
                    "normally_on_hand": ingredient.normally_on_hand,
                    "uses": 1,
                }
            else:
                row = rows[key]
                if quantified:
                    row["quantity"] += quantity
                row["normally_on_hand"] = row["normally_on_hand"] and ingredient.normally_on_hand
                row["uses"] += 1
    result = []
    for row in rows.values():
        result.append(
            {
                **row,
                "quantity_value": _decimal_text(row["quantity"]),
                "quantity_text": _quantity_text(row["quantity"], row["unit"]),
            }
        )
    return result


def selected_demand_rows(family, start_date, end_date, selection):
    if not isinstance(selection, dict):
        raise ValidationError({"selection": "Auswahl muss ein Objekt pro Bedarfszeile sein."})
    demand = aggregate_meal_demand(family, start_date, end_date)
    by_key = {row["key"]: row for row in demand}
    unknown = sorted(set(selection) - set(by_key))
    if unknown:
        raise ValidationError({"selection": "Der Essensplan hat sich geändert. Bitte Einkauf erneut prüfen."})
    selected = {}
    for key, choice in selection.items():
        if not isinstance(choice, dict) or not choice.get("missing", False):
            continue
        row = by_key[key]
        quantity_text = choice.get("quantity_text", row["quantity_text"])
        if quantity_text is None:
            quantity_text = ""
        quantity_text = str(quantity_text).strip()
        if len(quantity_text) > 40:
            raise ValidationError({"selection": "Mengenangaben dürfen höchstens 40 Zeichen lang sein."})
        selected[key] = {
            "key": key,
            "name": row["name"][:160],
            "quantity_text": quantity_text,
        }
    return selected


def _is_tracked_item_modified(tracked, item):
    return (
        item.version != tracked.shopping_item_version
        or item.name != tracked.generated_name
        or item.quantity != tracked.generated_quantity
    )


def build_transfer_diff(*, user, family, start_date, end_date, shopping_list, selection):
    if not can_access_shopping_list(user, shopping_list) or shopping_list.family_id != family.id:
        raise PermissionDenied("Einkaufsliste nicht gefunden oder nicht freigegeben.")
    desired = selected_demand_rows(family, start_date, end_date, selection)
    transfer = MealShoppingTransfer.objects.filter(
        family=family,
        start_date=start_date,
        end_date=end_date,
        shopping_list=shopping_list,
    ).first()
    tracked_by_key = {}
    if transfer:
        tracked_by_key = {
            item.demand_key: item
            for item in transfer.items.select_related("shopping_item").all()
        }

    actions = []
    for key, row in desired.items():
        tracked = tracked_by_key.get(key)
        item = tracked.shopping_item if tracked else None
        if not tracked or not item:
            actions.append({"action": "add", **row})
            continue
        if item.checked:
            actions.append({"action": "preserve_checked", "shopping_item": str(item.id), **row})
            continue
        if _is_tracked_item_modified(tracked, item):
            actions.append({"action": "preserve_modified", "shopping_item": str(item.id), **row})
            continue
        if item.name == row["name"] and item.quantity == row["quantity_text"]:
            actions.append({"action": "unchanged", "shopping_item": str(item.id), **row})
        else:
            actions.append({"action": "update", "shopping_item": str(item.id), **row})

    for key, tracked in tracked_by_key.items():
        if key in desired:
            continue
        item = tracked.shopping_item
        base = {
            "key": key,
            "name": tracked.generated_name,
            "quantity_text": tracked.generated_quantity,
            "shopping_item": str(item.id) if item else None,
        }
        if not item:
            actions.append({"action": "detach", **base})
        elif item.checked:
            actions.append({"action": "preserve_checked", **base})
        elif _is_tracked_item_modified(tracked, item):
            actions.append({"action": "preserve_modified", **base})
        else:
            actions.append({"action": "remove", **base})

    order = {
        "add": 0,
        "update": 1,
        "remove": 2,
        "preserve_checked": 3,
        "preserve_modified": 4,
        "unchanged": 5,
        "detach": 6,
    }
    actions.sort(key=lambda row: (order.get(row["action"], 99), row.get("name", "").casefold(), row["key"]))
    return actions


@transaction.atomic
def commit_transfer(*, user, family, start_date, end_date, shopping_list, selection):
    shopping_list = ShoppingList.objects.select_for_update().get(pk=shopping_list.pk)
    if not can_access_shopping_list(user, shopping_list) or shopping_list.family_id != family.id:
        raise PermissionDenied("Einkaufsliste nicht gefunden oder nicht freigegeben.")

    actions = build_transfer_diff(
        user=user,
        family=family,
        start_date=start_date,
        end_date=end_date,
        shopping_list=shopping_list,
        selection=selection,
    )
    desired = selected_demand_rows(family, start_date, end_date, selection)
    transfer, _ = MealShoppingTransfer.objects.select_for_update().get_or_create(
        family=family,
        start_date=start_date,
        end_date=end_date,
        shopping_list=shopping_list,
        defaults={"created_by": user},
    )
    tracked_by_key = {
        item.demand_key: item
        for item in transfer.items.select_for_update().select_related("shopping_item").all()
    }

    applied = []
    for action in actions:
        kind = action["action"]
        key = action["key"]
        row = desired.get(key)
        tracked = tracked_by_key.get(key)
        if kind == "add" and row:
            item = ShoppingItem.objects.create(
                shopping_list=shopping_list,
                name=row["name"],
                quantity=row["quantity_text"],
                added_by=user,
            )
            MealShoppingTransferItem.objects.update_or_create(
                transfer=transfer,
                demand_key=key,
                defaults={
                    "shopping_item": item,
                    "generated_name": item.name,
                    "generated_quantity": item.quantity,
                    "shopping_item_version": item.version,
                },
            )
            applied.append(kind)
        elif kind == "update" and row and tracked and tracked.shopping_item:
            item = tracked.shopping_item
            item.name = row["name"]
            item.quantity = row["quantity_text"]
            item.save(update_fields=["name", "quantity", "updated_at"])
            tracked.generated_name = item.name
            tracked.generated_quantity = item.quantity
            tracked.shopping_item_version = item.version
            tracked.save(update_fields=["generated_name", "generated_quantity", "shopping_item_version", "updated_at"])
            applied.append(kind)
        elif kind == "remove" and tracked:
            if tracked.shopping_item:
                tracked.shopping_item.delete()
            tracked.delete()
            applied.append(kind)
        elif kind == "detach" and tracked:
            tracked.delete()
            applied.append(kind)

    return {
        "actions": actions,
        "applied": applied,
        "transfer_id": str(transfer.id),
    }
