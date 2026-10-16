from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework import serializers

from entitlements.services import require_capability
from family.models import Family, Membership
from .models import (
    Expense,
    ExpenseLedger,
    ExpenseShare,
    ReceiptExtraction,
    Settlement,
    get_default_expense_ledger,
)
from .money import balance_summary, build_split, money
from .planning_serializers import RevisionCheckedPlanningSerializer


class LocalizedDecimalField(serializers.DecimalField):
    def to_internal_value(self, data):
        if isinstance(data, str):
            text = data.strip().replace(" ", "")
            if "," in text and "." in text:
                if text.rfind(",") > text.rfind("."):
                    text = text.replace(".", "").replace(",", ".")
                else:
                    text = text.replace(",", "")
            else:
                text = text.replace(",", ".")
            data = text
        return super().to_internal_value(data)


def _validate_currency(value):
    value = (value or "EUR").upper()
    if len(value) != 3 or not value.isalpha():
        raise serializers.ValidationError("Währung muss ein ISO-4217-Code mit drei Buchstaben sein.")
    return value


def _request_can_access_family(request, family):
    if not request or not request.user.is_authenticated:
        return False
    if request.user.is_superuser:
        require_capability(request.user, family, "expenses")
        return True
    allowed = Membership.objects.filter(
        family=family,
        user=request.user,
        family__status=Family.Status.ACTIVE,
    ).exists()
    if allowed:
        require_capability(request.user, family, "expenses")
    return allowed


FX_FIELDS = ("original_amount", "original_currency", "fx_rate")


def _apply_frozen_fx(attrs, instance, ledger):
    supplied = any(field in attrs for field in FX_FIELDS)
    existing_fx = bool(instance and instance.fx_rate is not None)
    ledger_changed = bool(instance and instance.ledger_id and instance.ledger_id != ledger.id)

    if existing_fx and not supplied and ("total_amount" in attrs or "currency" in attrs):
        raise serializers.ValidationError({
            "total_amount": "Bei einer FX-Ausgabe werden Basisbetrag und -währung aus Originalbetrag und eingefrorenem Kurs berechnet."
        })
    if existing_fx and ledger_changed and "fx_rate" not in attrs:
        raise serializers.ValidationError({
            "fx_rate": "Beim Wechsel des Abrechnungskreises muss der Kurs für dessen Basiswährung ausdrücklich bestätigt werden."
        })
    if not supplied:
        return attrs

    original_amount = attrs.get("original_amount", getattr(instance, "original_amount", None))
    original_currency = attrs.get("original_currency", getattr(instance, "original_currency", None))
    fx_rate = attrs.get("fx_rate", getattr(instance, "fx_rate", None))
    if original_amount is None or not original_currency or fx_rate is None:
        raise serializers.ValidationError({
            "fx": "Originalbetrag, Originalwährung und eingefrorener Kurs müssen gemeinsam angegeben werden."
        })
    if original_amount <= 0:
        raise serializers.ValidationError({"original_amount": "Originalbetrag muss größer als 0 sein."})
    if fx_rate <= 0:
        raise serializers.ValidationError({"fx_rate": "FX-Kurs muss größer als 0 sein."})

    original_currency = _validate_currency(original_currency)
    base_currency = ledger.base_currency.upper()
    if original_currency == base_currency and fx_rate != Decimal("1"):
        raise serializers.ValidationError({
            "fx_rate": "Bei identischer Original- und Basiswährung muss der Kurs 1 sein."
        })

    converted = money(original_amount * fx_rate)
    if converted <= 0:
        raise serializers.ValidationError({"fx_rate": "Der umgerechnete Betrag muss mindestens einen Cent ergeben."})
    if "total_amount" in attrs and attrs["total_amount"] is not None and money(attrs["total_amount"]) != converted:
        raise serializers.ValidationError({
            "total_amount": f"Basisbetrag wird aus Originalbetrag und FX-Kurs berechnet und muss {converted:.2f} {base_currency} ergeben."
        })
    if "currency" in attrs and attrs["currency"] and attrs["currency"].upper() != base_currency:
        raise serializers.ValidationError({
            "currency": f"Im FX-Modus ist die gespeicherte Ausgabenwährung die Ledger-Basiswährung {base_currency}."
        })

    attrs["original_amount"] = original_amount
    attrs["original_currency"] = original_currency
    attrs["fx_rate"] = fx_rate
    attrs["total_amount"] = converted
    attrs["currency"] = base_currency
    return attrs


def _ledger_default_participants(ledger, family):
    configured = [str(value) for value in (ledger.default_participants or [])]
    if configured:
        return configured
    return [str(value) for value in Membership.objects.filter(family=family).order_by("created_at").values_list("id", flat=True)]


def _ledger_default_values(ledger):
    return {str(key): Decimal(str(value)) for key, value in (ledger.default_split_values or {}).items()}


class ExpenseLedgerSerializer(RevisionCheckedPlanningSerializer):
    expected_children_amount = LocalizedDecimalField(max_digits=16, decimal_places=2, write_only=True, required=False)

    def create(self, validated_data):
        validated_data.pop("expected_children_amount", None)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        from .hierarchy_services import check_child_plan
        current = ExpenseLedger.objects.select_for_update().get(pk=instance.pk)
        check_child_plan(current, validated_data.pop("expected_children_amount", None))
        return super().update(current, validated_data)

    estimated_amount = LocalizedDecimalField(
        max_digits=12, decimal_places=2, allow_null=True, required=False, min_value=Decimal("0.00"),
    )
    budget_amount = LocalizedDecimalField(
        max_digits=12,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    default_participants = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    default_split_values = serializers.DictField(
        child=LocalizedDecimalField(max_digits=12, decimal_places=4),
        required=False,
    )

    def validate_base_currency(self, value):
        return _validate_currency(value)

    def validate_budget_amount(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Budget darf nicht negativ sein.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        if not family or not _request_can_access_family(request, family):
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        if self.instance and "family" in attrs and family.id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Die Familie eines Abrechnungskreises kann nicht geändert werden."})
        if self.instance and "base_currency" in attrs and attrs["base_currency"] != self.instance.base_currency:
            if self.instance.expenses.exists() or self.instance.budgets.exists():
                raise serializers.ValidationError({
                    "base_currency": "Die Basiswährung kann nach der ersten Ausgabe oder Budgetanlage nicht geändert werden."
                })
        if self.instance and self.instance.is_default and attrs.get("archived") is True:
            raise serializers.ValidationError({"archived": "Der Standard-Abrechnungskreis kann nicht archiviert werden."})

        split_type = attrs.get("default_split_type", getattr(self.instance, "default_split_type", ExpenseLedger.DefaultSplitType.EQUAL))
        participants = attrs.get("default_participants", getattr(self.instance, "default_participants", [])) or []
        values = attrs.get("default_split_values", getattr(self.instance, "default_split_values", {})) or {}
        participant_ids = {str(value) for value in participants}
        if participant_ids:
            found = set(str(value) for value in Membership.objects.filter(family=family, id__in=participants).values_list("id", flat=True))
            if participant_ids != found:
                raise serializers.ValidationError({"default_participants": "Mindestens eine konfigurierte Person gehört nicht zu dieser Familie."})
        if split_type == ExpenseLedger.DefaultSplitType.EQUAL:
            attrs["default_split_values"] = {}
        else:
            if not participant_ids:
                raise serializers.ValidationError({"default_participants": "Für Prozent- oder Anteilverteilung müssen feste Beteiligte gewählt werden."})
            normalized = {str(key): Decimal(str(value)) for key, value in values.items()}
            if set(normalized) != participant_ids:
                raise serializers.ValidationError({"default_split_values": "Für jede beteiligte Person ist ein Wert erforderlich."})
            if any(value <= 0 for value in normalized.values()):
                raise serializers.ValidationError({"default_split_values": "Alle Werte müssen größer als 0 sein."})
            if split_type == ExpenseLedger.DefaultSplitType.PERCENTAGE and sum(normalized.values(), Decimal("0")) != Decimal("100"):
                raise serializers.ValidationError({"default_split_values": "Prozentwerte müssen zusammen 100 ergeben."})
            attrs["default_split_values"] = {key: str(value) for key, value in normalized.items()}
        attrs["default_participants"] = [str(value) for value in participants]
        return attrs

    class Meta:
        model = ExpenseLedger
        fields = [
            "id",
            "family",
            "name",
            "base_currency",
            "budget_amount",
            "estimated_amount",
            "expected_updated_at",
            "expected_children_amount",
            "is_default",
            "archived",
            "default_split_type",
            "default_participants",
            "default_split_values",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["is_default", "created_at", "updated_at"]


class ExpenseShareSerializer(serializers.ModelSerializer):
    member_name = serializers.SerializerMethodField()

    def get_member_name(self, obj):
        return obj.member.display_name or obj.member.user.username

    class Meta:
        model = ExpenseShare
        fields = ["id", "member", "member_name", "amount", "split_type", "split_value"]


class ReceiptExtractionSerializer(serializers.ModelSerializer):
    quality_warnings = serializers.SerializerMethodField()
    structured_data = serializers.SerializerMethodField()

    def get_quality_warnings(self, obj):
        warnings = (obj.structured_data or {}).get("quality_warnings", [])
        return [value for value in warnings if value in {"low_resolution", "dark"}]

    def get_structured_data(self, obj):
        data = obj.structured_data or {}
        if data.get("schema_version") != 2:
            return {}
        public_keys = (
            "schema_version",
            "extractor_version",
            "ocr_confidence",
            "semantic_confidence",
            "fields",
            "total_candidates",
            "line_items",
            "reconciliation",
            "review",
        )
        return {key: data[key] for key in public_keys if key in data}

    class Meta:
        model = ReceiptExtraction
        fields = [
            "id", "status", "merchant", "date", "total", "subtotal", "tax", "currency",
            "field_confidences", "quality_warnings", "structured_data", "parser_version", "processed_at",
        ]


class ExpenseSerializer(serializers.ModelSerializer):
    receipt_mime = serializers.SerializerMethodField()

    def get_receipt_mime(self, obj):
        return obj.receipt_document.mime_type if obj.receipt_document_id else obj.receipt_mime

    shares = ExpenseShareSerializer(many=True, read_only=True)
    extraction = ReceiptExtractionSerializer(read_only=True)
    paid_by_name = serializers.SerializerMethodField()
    receipt_available = serializers.SerializerMethodField()
    total_amount = LocalizedDecimalField(max_digits=12, decimal_places=2, allow_null=True, required=False)
    original_amount = LocalizedDecimalField(max_digits=12, decimal_places=2, allow_null=True, required=False)
    original_currency = serializers.CharField(max_length=3, allow_null=True, allow_blank=True, required=False)
    fx_rate = LocalizedDecimalField(max_digits=20, decimal_places=10, allow_null=True, required=False)
    participants = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    split_type = serializers.ChoiceField(choices=ExpenseShare.SplitType.choices, write_only=True, required=False)
    split_values = serializers.DictField(child=LocalizedDecimalField(max_digits=12, decimal_places=4), write_only=True, required=False)
    client_request_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    finalize = serializers.BooleanField(write_only=True, required=False, default=False)

    def get_paid_by_name(self, obj):
        if obj.paid_by_id is None:
            return None
        return obj.paid_by.display_name or obj.paid_by.user.username

    def get_receipt_available(self, obj):
        return bool(obj.receipt_document_id or obj.receipt_mime)

    def validate_currency(self, value):
        return _validate_currency(value)

    def validate_original_currency(self, value):
        if value in (None, ""):
            return None
        return _validate_currency(value)

    def validate_total_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Der Gesamtbetrag muss größer als 0 sein.")
        return value

    def validate_original_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Originalbetrag muss größer als 0 sein.")
        return value

    def validate_fx_rate(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("FX-Kurs muss größer als 0 sein.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        if not family or not request or not request.user.is_authenticated:
            raise serializers.ValidationError({"family": "Eine aktive Familie ist erforderlich."})
        if self.instance and "family" in attrs and family.id != self.instance.family_id:
            raise serializers.ValidationError({"family": "Die Familie einer bestehenden Ausgabe kann nicht geändert werden."})
        membership = Membership.objects.filter(family=family, user=request.user, family__status=Family.Status.ACTIVE).first()
        if not membership and not request.user.is_superuser:
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})

        funding_source = attrs.get(
            "funding_source",
            getattr(self.instance, "funding_source", Expense.FundingSource.MEMBER),
        )
        explicit_paid_by = "paid_by" in attrs
        if funding_source == Expense.FundingSource.SHARED:
            if explicit_paid_by and attrs.get("paid_by") is not None:
                raise serializers.ValidationError({"paid_by": "Bei gemeinsamer Zahlung darf kein persönlicher Zahler gesetzt sein."})
            attrs["paid_by"] = None
        else:
            paid_by = attrs.get("paid_by") or getattr(self.instance, "paid_by", None) or membership
            if not paid_by or paid_by.family_id != family.id:
                raise serializers.ValidationError({"paid_by": "Zahler gehört nicht zu dieser Familie."})
            attrs["paid_by"] = paid_by

        ledger = attrs.get("ledger") or getattr(self.instance, "ledger", None)
        if ledger is None:
            ledger = get_default_expense_ledger(family)
        if ledger.family_id != family.id:
            raise serializers.ValidationError({"ledger": "Abrechnungskreis gehört nicht zu dieser Familie."})
        if ledger.archived:
            raise serializers.ValidationError({"ledger": "Archivierter Abrechnungskreis kann nicht verwendet werden."})
        attrs["ledger"] = ledger
        _apply_frozen_fx(attrs, self.instance, ledger)

        participants = attrs.get("participants")
        has_existing_shares = bool(self.instance and self.instance.shares.exists())
        # Defaults accelerate new capture; a posted shared booking must not
        # acquire personal debts through an implicit update.
        can_apply_defaults = self.instance is None or self.instance.status == Expense.Status.DRAFT
        if can_apply_defaults and funding_source == Expense.FundingSource.MEMBER and participants is None and not has_existing_shares:
            participants = _ledger_default_participants(ledger, family)
            attrs["participants"] = participants
            attrs.setdefault("split_type", ledger.default_split_type or ExpenseShare.SplitType.EQUAL)
            if attrs["split_type"] != ExpenseShare.SplitType.EQUAL:
                attrs.setdefault("split_values", _ledger_default_values(ledger))

        if funding_source == Expense.FundingSource.SHARED:
            if participants is not None:
                raise serializers.ValidationError({
                    "participants": "Gemeinsam bezahlte Ausgaben erzeugen keine persönliche Schuldaufteilung."
                })
            if "split_values" in attrs:
                raise serializers.ValidationError({
                    "split_values": "Gemeinsam bezahlte Ausgaben haben keine persönliche Schuldaufteilung."
                })
        elif participants is not None:
            unique = {str(value) for value in participants}
            found = set(str(value) for value in Membership.objects.filter(family=family, id__in=participants).values_list("id", flat=True))
            if not unique:
                raise serializers.ValidationError({"participants": "Mindestens eine beteiligte Person ist erforderlich."})
            if unique != found:
                raise serializers.ValidationError({"participants": "Mindestens eine beteiligte Person gehört nicht zu dieser Familie."})

        finalize = attrs.get("finalize", False)
        current_status = getattr(self.instance, "status", None)
        will_post = self.instance is None or current_status == Expense.Status.POSTED or finalize
        if will_post:
            total = attrs.get("total_amount", getattr(self.instance, "total_amount", None))
            if total is None:
                raise serializers.ValidationError({"total_amount": "Gesamtbetrag ist erforderlich."})
            if funding_source == Expense.FundingSource.MEMBER and participants is None and not has_existing_shares:
                raise serializers.ValidationError({"participants": "Beteiligte sind erforderlich."})
        if (
            self.instance
            and current_status == Expense.Status.POSTED
            and funding_source == Expense.FundingSource.MEMBER
            and "total_amount" in attrs
            and participants is None
        ):
            raise serializers.ValidationError({"participants": "Bei geändertem Gesamtbetrag muss die Aufteilung bestätigt werden."})
        return attrs

    def _write_shares(self, expense, participants, split_type, split_values):
        if participants is None:
            return
        try:
            split = build_split(expense.total_amount, participants, split_type, split_values)
        except ValueError as exc:
            raise serializers.ValidationError({"split": str(exc)}) from exc
        members = {str(member.id): member for member in Membership.objects.filter(family=expense.family, id__in=participants)}
        normalized_values = {str(key): Decimal(str(value)) for key, value in (split_values or {}).items()}
        expense.shares.all().delete()
        ExpenseShare.objects.bulk_create([
            ExpenseShare(
                expense=expense,
                member=members[member_id],
                amount=amount,
                split_type=split_type,
                split_value=None if split_type == ExpenseShare.SplitType.EQUAL else normalized_values.get(member_id),
            )
            for member_id, amount in split.items()
        ])

    @transaction.atomic
    def create(self, validated_data):
        participants = validated_data.pop("participants", None)
        split_type = validated_data.pop("split_type", ExpenseShare.SplitType.EQUAL)
        split_values = validated_data.pop("split_values", None)
        validated_data.pop("finalize", None)
        request_user = self.context["request"].user
        validated_data["created_by"] = request_user
        validated_data["status"] = Expense.Status.POSTED
        validated_data.setdefault("source", Expense.Source.MANUAL)
        validated_data["title"] = (validated_data.get("title") or "").strip() or "Ausgabe"

        request_id = validated_data.get("client_request_id")
        if request_id:
            existing = Expense.objects.filter(
                family=validated_data["family"],
                created_by=request_user,
                client_request_id=request_id,
            ).first()
            if existing:
                return existing

        try:
            with transaction.atomic():
                expense = Expense.objects.create(**validated_data)
        except IntegrityError:
            if request_id:
                existing = Expense.objects.filter(
                    family=validated_data["family"],
                    created_by=request_user,
                    client_request_id=request_id,
                ).first()
                if existing:
                    return existing
            raise

        if expense.funding_source == Expense.FundingSource.MEMBER:
            self._write_shares(expense, participants, split_type, split_values)
        return expense

    @transaction.atomic
    def update(self, instance, validated_data):
        participants = validated_data.pop("participants", None)
        split_type = validated_data.pop("split_type", None)
        split_values = validated_data.pop("split_values", None)
        validated_data.pop("client_request_id", None)
        finalize = validated_data.pop("finalize", False)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if finalize:
            instance.status = Expense.Status.POSTED
            if instance.receipt_status in {Expense.ReceiptStatus.REVIEW, Expense.ReceiptStatus.FAILED}:
                instance.receipt_status = Expense.ReceiptStatus.READY
        instance.save()
        if instance.funding_source == Expense.FundingSource.SHARED:
            instance.shares.all().delete()
        elif participants is not None:
            self._write_shares(instance, participants, split_type or ExpenseShare.SplitType.EQUAL, split_values)
        elif split_type is not None and instance.shares.exists():
            current = [share.member_id for share in instance.shares.all()]
            self._write_shares(instance, current, split_type, split_values)
        extraction = getattr(instance, "extraction", None)
        if finalize and extraction:
            extraction.status = ReceiptExtraction.Status.READY
            extraction.save(update_fields=["status", "updated_at"])
        return instance

    class Meta:
        model = Expense
        fields = [
            "id", "family", "ledger", "title", "merchant", "category", "occurred_at", "total_amount", "currency",
            "original_amount", "original_currency", "fx_rate", "funding_source", "paid_by", "paid_by_name",
            "created_by", "client_request_id", "receipt_status", "receipt_available", "receipt_mime", "source", "status", "notes",
            "shares", "extraction", "participants", "split_type", "split_values", "finalize", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by", "receipt_status", "source", "status"]
        extra_kwargs = {
            "paid_by": {"required": False, "allow_null": True},
            "ledger": {"required": False, "allow_null": True},
        }
        validators = []


class SettlementSerializer(serializers.ModelSerializer):
    from_name = serializers.SerializerMethodField()
    to_name = serializers.SerializerMethodField()

    def get_from_name(self, obj):
        return obj.from_member.display_name or obj.from_member.user.username

    def get_to_name(self, obj):
        return obj.to_member.display_name or obj.to_member.user.username

    def validate_currency(self, value):
        return _validate_currency(value)

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        allowed = family and _request_can_access_family(request, family)
        if not allowed:
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        sender = attrs.get("from_member") or getattr(self.instance, "from_member", None)
        receiver = attrs.get("to_member") or getattr(self.instance, "to_member", None)
        if not sender or not receiver or sender.family_id != family.id or receiver.family_id != family.id:
            raise serializers.ValidationError("Beide Personen müssen zur Familie gehören.")
        if sender.id == receiver.id:
            raise serializers.ValidationError("Sender und Empfänger dürfen nicht identisch sein.")

        ledger = attrs.get("ledger") or getattr(self.instance, "ledger", None)
        if ledger is None:
            ledger = get_default_expense_ledger(family)
        if ledger.family_id != family.id:
            raise serializers.ValidationError({"ledger": "Abrechnungskreis gehört nicht zu dieser Familie."})
        if ledger.archived:
            raise serializers.ValidationError({"ledger": "Archivierter Abrechnungskreis kann nicht verwendet werden."})
        attrs["ledger"] = ledger

        amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0")))
        if amount <= 0:
            raise serializers.ValidationError({"amount": "Betrag muss größer als 0 sein."})

        currency = attrs.get("currency") or getattr(self.instance, "currency", "EUR")
        summary = balance_summary(family, currency, ledger=ledger)
        sender_row = summary.get(str(sender.id))
        receiver_row = summary.get(str(receiver.id))
        sender_balance = sender_row["balance"] if sender_row else Decimal("0.00")
        receiver_balance = receiver_row["balance"] if receiver_row else Decimal("0.00")
        if sender_balance >= 0 or receiver_balance <= 0:
            raise serializers.ValidationError({"amount": "Diese Abrechnung passt nicht zum aktuellen Saldo."})
        maximum = min(-sender_balance, receiver_balance)
        if amount > maximum:
            raise serializers.ValidationError({"amount": f"Höchstens {maximum:.2f} {currency} können abgerechnet werden."})
        return attrs

    class Meta:
        model = Settlement
        fields = [
            "id", "family", "ledger", "from_member", "from_name", "to_member", "to_name",
            "amount", "currency", "settled_at", "created_by", "note", "voided_at", "created_at",
        ]
        read_only_fields = ["created_by", "voided_at"]
        extra_kwargs = {"ledger": {"required": False, "allow_null": True}}
