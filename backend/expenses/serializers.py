from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from family.models import Family, Membership
from .models import Expense, ExpenseShare, ReceiptExtraction, Settlement
from .money import build_split


class ExpenseShareSerializer(serializers.ModelSerializer):
    member_name = serializers.SerializerMethodField()

    def get_member_name(self, obj):
        return obj.member.display_name or obj.member.user.username

    class Meta:
        model = ExpenseShare
        fields = ["id", "member", "member_name", "amount", "split_type"]


class ReceiptExtractionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptExtraction
        fields = [
            "id", "status", "merchant", "date", "total", "subtotal", "tax", "currency",
            "structured_data", "field_confidences", "parser_version", "processed_at", "error",
        ]


class ExpenseSerializer(serializers.ModelSerializer):
    shares = ExpenseShareSerializer(many=True, read_only=True)
    extraction = ReceiptExtractionSerializer(read_only=True)
    paid_by_name = serializers.SerializerMethodField()
    receipt_available = serializers.SerializerMethodField()
    participants = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    split_type = serializers.ChoiceField(choices=ExpenseShare.SplitType.choices, write_only=True, required=False, default=ExpenseShare.SplitType.EQUAL)
    split_values = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=4), write_only=True, required=False)
    finalize = serializers.BooleanField(write_only=True, required=False, default=False)

    def get_paid_by_name(self, obj):
        return obj.paid_by.display_name or obj.paid_by.user.username

    def get_receipt_available(self, obj):
        return bool(obj.receipt_content)

    def validate_currency(self, value):
        value = (value or "EUR").upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Währung muss ein ISO-4217-Code mit drei Buchstaben sein.")
        return value

    def validate_total_amount(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Der Gesamtbetrag muss größer als 0 sein.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        if not family or not request or not request.user.is_authenticated:
            raise serializers.ValidationError({"family": "Eine aktive Familie ist erforderlich."})
        membership = Membership.objects.filter(family=family, user=request.user, family__status=Family.Status.ACTIVE).first()
        if not membership and not request.user.is_superuser:
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        paid_by = attrs.get("paid_by") or getattr(self.instance, "paid_by", None) or membership
        if not paid_by or paid_by.family_id != family.id:
            raise serializers.ValidationError({"paid_by": "Zahler gehört nicht zu dieser Familie."})
        attrs["paid_by"] = paid_by

        participants = attrs.get("participants")
        if participants is not None:
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
            if self.instance is None and participants is None:
                raise serializers.ValidationError({"participants": "Beteiligte sind erforderlich."})
            if finalize and participants is None and not self.instance.shares.exists():
                raise serializers.ValidationError({"participants": "Beteiligte sind erforderlich."})
        if self.instance and current_status == Expense.Status.POSTED and "total_amount" in attrs and participants is None:
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
        expense.shares.all().delete()
        ExpenseShare.objects.bulk_create([
            ExpenseShare(expense=expense, member=members[member_id], amount=amount, split_type=split_type)
            for member_id, amount in split.items()
        ])

    @transaction.atomic
    def create(self, validated_data):
        participants = validated_data.pop("participants", None)
        split_type = validated_data.pop("split_type", ExpenseShare.SplitType.EQUAL)
        split_values = validated_data.pop("split_values", None)
        validated_data.pop("finalize", None)
        validated_data["created_by"] = self.context["request"].user
        validated_data["status"] = Expense.Status.POSTED
        validated_data.setdefault("source", Expense.Source.MANUAL)
        expense = Expense.objects.create(**validated_data)
        self._write_shares(expense, participants, split_type, split_values)
        return expense

    @transaction.atomic
    def update(self, instance, validated_data):
        participants = validated_data.pop("participants", None)
        split_type = validated_data.pop("split_type", None)
        split_values = validated_data.pop("split_values", None)
        finalize = validated_data.pop("finalize", False)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if finalize:
            instance.status = Expense.Status.POSTED
            if instance.receipt_status in {Expense.ReceiptStatus.REVIEW, Expense.ReceiptStatus.FAILED}:
                instance.receipt_status = Expense.ReceiptStatus.READY
        instance.save()
        if participants is not None:
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
            "id", "family", "title", "merchant", "occurred_at", "total_amount", "currency",
            "paid_by", "paid_by_name", "created_by", "receipt_status", "receipt_available", "source",
            "status", "notes", "shares", "extraction", "participants", "split_type", "split_values",
            "finalize", "created_at", "updated_at",
        ]
        read_only_fields = ["created_by", "receipt_status", "source", "status"]
        extra_kwargs = {"paid_by": {"required": False}}


class SettlementSerializer(serializers.ModelSerializer):
    from_name = serializers.SerializerMethodField()
    to_name = serializers.SerializerMethodField()

    def get_from_name(self, obj):
        return obj.from_member.display_name or obj.from_member.user.username

    def get_to_name(self, obj):
        return obj.to_member.display_name or obj.to_member.user.username

    def validate_currency(self, value):
        value = (value or "EUR").upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Währung muss ein ISO-4217-Code mit drei Buchstaben sein.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        family = attrs.get("family") or getattr(self.instance, "family", None)
        allowed = family and (request.user.is_superuser or Membership.objects.filter(family=family, user=request.user, family__status=Family.Status.ACTIVE).exists())
        if not allowed:
            raise serializers.ValidationError({"family": "Familie ist für diesen Benutzer nicht verfügbar."})
        sender = attrs.get("from_member") or getattr(self.instance, "from_member", None)
        receiver = attrs.get("to_member") or getattr(self.instance, "to_member", None)
        if not sender or not receiver or sender.family_id != family.id or receiver.family_id != family.id:
            raise serializers.ValidationError("Beide Personen müssen zur Familie gehören.")
        if sender.id == receiver.id:
            raise serializers.ValidationError("Sender und Empfänger dürfen nicht identisch sein.")
        amount = attrs.get("amount", getattr(self.instance, "amount", Decimal("0")))
        if amount <= 0:
            raise serializers.ValidationError({"amount": "Betrag muss größer als 0 sein."})
        return attrs

    class Meta:
        model = Settlement
        fields = ["id", "family", "from_member", "from_name", "to_member", "to_name", "amount", "currency", "settled_at", "created_by", "note", "voided_at", "created_at"]
        read_only_fields = ["created_by", "voided_at"]
