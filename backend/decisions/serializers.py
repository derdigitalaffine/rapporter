from django.utils import timezone
from rest_framework import serializers

from .models import Decision


class DecisionContextSerializer(serializers.Serializer):
    type = serializers.CharField(max_length=64)
    id = serializers.UUIDField()


class DecisionCreateSerializer(serializers.Serializer):
    family = serializers.UUIDField()
    question = serializers.CharField(max_length=500, trim_whitespace=True)
    mode = serializers.ChoiceField(choices=Decision.Mode.choices, default=Decision.Mode.SINGLE)
    anonymous = serializers.BooleanField(default=False)
    closes_at = serializers.DateTimeField(required=False, allow_null=True)
    options = serializers.ListField(
        child=serializers.CharField(max_length=240, trim_whitespace=True),
        min_length=2,
        max_length=10,
    )
    context = DecisionContextSerializer(required=False, allow_null=True)

    def validate_question(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("question_required")
        return value

    def validate_options(self, value):
        labels = [label.strip() for label in value]
        if any(not label for label in labels):
            raise serializers.ValidationError("option_label_required")
        normalized = [label.casefold() for label in labels]
        if len(set(normalized)) != len(normalized):
            raise serializers.ValidationError("duplicate_options")
        return labels

    def validate_closes_at(self, value):
        if value is not None and value <= timezone.now():
            raise serializers.ValidationError("deadline_must_be_future")
        return value


class DecisionRatingSerializer(serializers.Serializer):
    option_id = serializers.UUIDField()
    score = serializers.IntegerField(min_value=1, max_value=5)


class DecisionVoteSerializer(serializers.Serializer):
    option_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        max_length=10,
        required=False,
        default=list,
    )
    ratings = DecisionRatingSerializer(many=True, required=False, default=list)

    def validate_option_ids(self, value):
        if len(set(value)) != len(value):
            raise serializers.ValidationError("duplicate_option_ids")
        return value

    def validate_ratings(self, value):
        option_ids = [row["option_id"] for row in value]
        if len(set(option_ids)) != len(option_ids):
            raise serializers.ValidationError("duplicate_option_ids")
        return value
