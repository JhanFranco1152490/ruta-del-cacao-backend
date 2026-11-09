from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import RejectUnknownFieldsMixin
from apps.common.validators import validate_not_future

from .models import (
    MAX_LINES,
    MAX_PRICE_PER_KG,
    NOTES_MAX_LENGTH,
    VOID_REASON_MAX_LENGTH,
    Grade,
)

DUPLICATE_LINE = "Ese lote y calibre ya está en otra línea."


class SaleLineRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    lot_id = serializers.UUIDField()
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = serializers.DecimalField(
        max_digits=7,
        decimal_places=1,
        min_value=Decimal("0.1"),
        error_messages={"max_decimal_places": "Usa máximo 1 decimal."},
    )
    price_per_kg = serializers.IntegerField(min_value=1, max_value=MAX_PRICE_PER_KG)


class SaleCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    farm_id = serializers.UUIDField()
    buyer_id = serializers.UUIDField()
    sale_date = serializers.DateField(validators=[validate_not_future])
    notes = serializers.CharField(max_length=NOTES_MAX_LENGTH, required=False, allow_blank=True)
    lines = SaleLineRequestSerializer(many=True, min_length=1, max_length=MAX_LINES)

    def validate_lines(self, lines):
        seen = set()
        for line in lines:
            key = (line["lot_id"], line["grade"])
            if key in seen:
                raise serializers.ValidationError(DUPLICATE_LINE)
            seen.add(key)
        return lines


class BuyerOptionsQuerySerializer(serializers.Serializer):
    producer = serializers.UUIDField(required=False)


class SaleVoidRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=VOID_REASON_MAX_LENGTH)
