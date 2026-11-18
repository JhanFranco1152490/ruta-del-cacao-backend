from datetime import date
from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.figures import one_decimal

from .report import DATE, KG, KINDS, PCT

# Sin docstrings en las clases: drf-spectacular los publicaría como descripción del componente.


def cell(value, kind: str):
    """Un valor como lo lee el cliente: kg y porcentajes como texto con un decimal (como el resto
    de la API), fechas en ISO, pesos y conteos como enteros y lo que falta como `null`."""
    if value is None:
        return None
    if kind in (KG, PCT):
        return str(one_decimal(Decimal(value)))
    if kind == DATE and isinstance(value, date):
        return value.isoformat()
    return value


# Una celda: texto, número entero o `null`.
CELL_SCHEMA = {"oneOf": [{"type": "string"}, {"type": "integer"}], "nullable": True}


class ReportFilterSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    text = serializers.CharField()
    id = serializers.CharField(allow_null=True)


class ReportColumnSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.ChoiceField(choices=KINDS)


class ReportTotalSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    kind = serializers.ChoiceField(choices=KINDS)
    value = serializers.SerializerMethodField()

    @extend_schema_field(CELL_SCHEMA)
    def get_value(self, total):
        return cell(total.value, total.kind)


class ReportSerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    generated_at = serializers.DateTimeField()
    generated_by = serializers.CharField()
    filters = ReportFilterSerializer(many=True)
    columns = ReportColumnSerializer(many=True)
    rows = serializers.SerializerMethodField()
    totals = ReportTotalSerializer(many=True)

    @extend_schema_field(
        {"type": "array", "items": {"type": "object", "additionalProperties": CELL_SCHEMA}}
    )
    def get_rows(self, report):
        return [
            {column.key: cell(row[column.key], column.kind) for column in report.columns}
            for row in report.rows
        ]
