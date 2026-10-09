from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

from .models import Expense, Settlement

CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def _to_cents(value):
    return int((money(value) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _from_cents(value):
    return (Decimal(value) / Decimal(100)).quantize(CENT)


def _apportion(total, weighted_members):
    total_cents = _to_cents(total)
    rows = [(str(member_id), Decimal(str(weight))) for member_id, weight in weighted_members]
    if not rows:
        raise ValueError("Mindestens eine beteiligte Person ist erforderlich.")
    if any(weight <= 0 for _, weight in rows):
        raise ValueError("Anteile müssen größer als 0 sein.")
    weight_sum = sum(weight for _, weight in rows)
    raw = []
    allocated = 0
    for member_id, weight in rows:
        exact = Decimal(total_cents) * weight / weight_sum
        base = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        raw.append((member_id, base, exact - Decimal(base)))
        allocated += base
    remainder = total_cents - allocated
    raw.sort(key=lambda item: (-item[2], item[0]))
    result = {member_id: base for member_id, base, _ in raw}
    for index in range(remainder):
        result[raw[index % len(raw)][0]] += 1
    return {member_id: _from_cents(cents) for member_id, cents in result.items()}


def build_split(total, participant_ids, split_type="equal", values=None):
    ids = sorted({str(value) for value in participant_ids})
    if not ids:
        raise ValueError("Mindestens eine beteiligte Person ist erforderlich.")
    total = money(total)
    values = {str(key): Decimal(str(value)) for key, value in (values or {}).items()}
    if split_type == "equal":
        return _apportion(total, [(member_id, 1) for member_id in ids])
    if split_type == "exact":
        if set(values) != set(ids):
            raise ValueError("Für jede beteiligte Person ist ein exakter Betrag erforderlich.")
        result = {member_id: money(values[member_id]) for member_id in ids}
        if sum(result.values(), Decimal("0.00")) != total:
            raise ValueError("Die exakten Beträge müssen zusammen dem Gesamtbetrag entsprechen.")
        if any(value < 0 for value in result.values()):
            raise ValueError("Beträge dürfen nicht negativ sein.")
        return result
    if split_type == "percentage":
        if set(values) != set(ids):
            raise ValueError("Für jede beteiligte Person ist ein Prozentwert erforderlich.")
        if sum(values.values(), Decimal("0")) != Decimal("100"):
            raise ValueError("Prozentwerte müssen zusammen 100 ergeben.")
        return _apportion(total, [(member_id, values[member_id]) for member_id in ids])
    if split_type == "shares":
        if set(values) != set(ids):
            raise ValueError("Für jede beteiligte Person ist ein Anteil erforderlich.")
        return _apportion(total, [(member_id, values[member_id]) for member_id in ids])
    raise ValueError("Unbekannter Aufteilungstyp.")


def balance_summary(family, currency="EUR"):
    currency = currency.upper()
    members = list(family.memberships.select_related("user").order_by("created_at"))
    summary = {
        str(member.id): {
            "member": member,
            "paid": Decimal("0.00"),
            "share": Decimal("0.00"),
            "settled_sent": Decimal("0.00"),
            "settled_received": Decimal("0.00"),
            "balance": Decimal("0.00"),
        }
        for member in members
    }
    expenses = Expense.objects.filter(family=family, currency=currency, status=Expense.Status.POSTED).prefetch_related("shares")
    for expense in expenses:
        if expense.total_amount is None:
            continue
        payer = summary.get(str(expense.paid_by_id))
        if payer:
            payer["paid"] += expense.total_amount
            payer["balance"] += expense.total_amount
        for share in expense.shares.all():
            row = summary.get(str(share.member_id))
            if row:
                row["share"] += share.amount
                row["balance"] -= share.amount
    settlements = Settlement.objects.filter(family=family, currency=currency, voided_at__isnull=True)
    for settlement in settlements:
        sender = summary.get(str(settlement.from_member_id))
        receiver = summary.get(str(settlement.to_member_id))
        if sender:
            sender["settled_sent"] += settlement.amount
            sender["balance"] += settlement.amount
        if receiver:
            receiver["settled_received"] += settlement.amount
            receiver["balance"] -= settlement.amount
    for row in summary.values():
        for key in ("paid", "share", "settled_sent", "settled_received", "balance"):
            row[key] = money(row[key])
    return summary


def simplify_balances(summary):
    debtors = sorted(
        [(member_id, -row["balance"]) for member_id, row in summary.items() if row["balance"] < 0],
        key=lambda item: (-item[1], item[0]),
    )
    creditors = sorted(
        [(member_id, row["balance"]) for member_id, row in summary.items() if row["balance"] > 0],
        key=lambda item: (-item[1], item[0]),
    )
    transfers = []
    debtor_index = creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor_id, owed = debtors[debtor_index]
        creditor_id, due = creditors[creditor_index]
        amount = money(min(owed, due))
        if amount > 0:
            transfers.append({"from": debtor_id, "to": creditor_id, "amount": amount})
        owed = money(owed - amount)
        due = money(due - amount)
        debtors[debtor_index] = (debtor_id, owed)
        creditors[creditor_index] = (creditor_id, due)
        if owed == 0:
            debtor_index += 1
        if due == 0:
            creditor_index += 1
    return transfers
