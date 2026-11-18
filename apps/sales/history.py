"""Las ventas en la historia de un lote: una etapa por venta con líneas de este lote, también las
anuladas, y lo vendido. Ni el precio ni el valor: la historia es del lote, no de lo que se
cobró."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db.models import Sum
from rest_framework import serializers

from apps.common.contracts.lot_history import LotHistoryStage, LotSold

from .models import Grade, SaleLine

ZERO = Decimal("0.0")


@dataclass(frozen=True)
class SaleLineData:
    grade: str
    quantity_kg: Decimal


@dataclass(frozen=True)
class SaleData:
    sale_id: Any
    # Como se muestra en Ventas (`V-0012`).
    number: str
    buyer: str
    # Solo las líneas de este lote, por calibre.
    lines: tuple[SaleLineData, ...]
    # Una venta anulada sigue en la historia, con cuándo y por qué se anuló.
    voided_at: datetime | None
    void_reason: str | None


def sales_history(lot_id) -> list[LotHistoryStage]:
    lines = (
        SaleLine.objects.filter(lot_id=lot_id)
        .select_related("sale__buyer")
        .order_by("sale__sale_date", "sale__created_at", "sale__number", "grade")
    )
    sales: dict[Any, tuple] = {}
    for line in lines:
        sale, sale_lines = sales.setdefault(line.sale_id, (line.sale, []))
        sale_lines.append(SaleLineData(grade=line.grade, quantity_kg=line.quantity_kg))
    return [
        LotHistoryStage.on(
            "sale",
            sale.sale_date,
            recorded_at=sale.created_at,
            data=SaleData(
                sale_id=sale.pk,
                number=sale.code,
                buyer=sale.buyer.name,
                lines=tuple(sale_lines),
                voided_at=sale.voided_at,
                void_reason=sale.void_reason if sale.voided_at is not None else None,
            ),
        )
        for sale, sale_lines in sales.values()
    ]


def sold_now(lot_id) -> LotSold:
    """Lo vendido del lote en ventas registradas: las anuladas devolvieron sus kilos."""
    sold = SaleLine.objects.filter(lot_id=lot_id, sale__voided_at__isnull=True).aggregate(
        kg=Sum("quantity_kg")
    )["kg"]
    return LotSold(sold_kg=sold if sold is not None else ZERO)


class SaleLineStageSerializer(serializers.Serializer):
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = serializers.DecimalField(max_digits=7, decimal_places=1)


class SaleStageSerializer(serializers.Serializer):
    sale_id = serializers.UUIDField()
    number = serializers.CharField()
    buyer = serializers.CharField()
    lines = SaleLineStageSerializer(many=True)
    voided_at = serializers.DateTimeField(allow_null=True)
    void_reason = serializers.CharField(allow_null=True)
