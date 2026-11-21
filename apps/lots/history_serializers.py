"""Cómo se publica la historia de un lote.

Cada etapa va con su `kind`, su fecha, su hora y sus datos bajo una clave con el nombre de su
`kind`. Los datos de cada tipo los serializa el serializer que registró su app, así que el esquema
es un `oneOf` por `kind`. Este módulo se importa desde la vista, que Django carga con las URL,
después de que todas las apps registraron sus serializers.
"""

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from apps.common.contracts.lot_history import STAGE_KINDS, stage_serializers
from apps.common.territorial import get_municipality

from .choices import LotStatus

_entry_classes: dict[str, type[serializers.Serializer]] = {}


def stage_entry_serializer(kind: str) -> type[serializers.Serializer]:
    """La clase que publica una etapa de `kind`. Se crea una vez por tipo, para que el esquema
    tenga un componente estable por cada uno."""
    if kind not in _entry_classes:
        data = stage_serializers(source="data")[kind]
        name = "".join(part.title() for part in kind.split("_"))
        _entry_classes[kind] = type(
            f"LotHistory{name}StageSerializer",
            (serializers.Serializer,),
            {
                "kind": serializers.ChoiceField(choices=[kind]),
                "occurred_on": serializers.DateField(),
                "occurred_at": serializers.DateTimeField(allow_null=True),
                kind: data,
            },
        )
    return _entry_classes[kind]


@extend_schema_field(
    PolymorphicProxySerializer(
        component_name="LotHistoryStage",
        serializers={kind: stage_entry_serializer(kind) for kind in STAGE_KINDS},
        resource_type_field_name="kind",
    )
)
class LotHistoryStageField(serializers.Field):
    def to_representation(self, stage):
        return stage_entry_serializer(stage.kind)(stage).data


class LotHistoryLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LotStatus.choices)
    created_at = serializers.DateTimeField()


class LotHistoryProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, producer) -> str:
        return f"{producer.first_name} {producer.last_name}".strip()


class LotHistoryFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    municipality = serializers.SerializerMethodField()

    def get_municipality(self, farm) -> str:
        return get_municipality(farm.municipality_code).name


class LotHistoryPlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField(allow_blank=True)


class LotHistoryHarvestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    harvest_date = serializers.DateField()


class LotHistoryOriginSerializer(serializers.Serializer):
    # Todo sale de la cosecha del lote, que la consulta del lote ya trae con su parcela, su finca y
    # su productor.
    producer = LotHistoryProducerSerializer(source="harvest.plot.farm.producer")
    farm = LotHistoryFarmSerializer(source="harvest.plot.farm")
    plot = LotHistoryPlotSerializer(source="harvest.plot")
    harvest = LotHistoryHarvestSerializer()


def _kilograms():
    return serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True)


class LotHistoryCurrentSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=LotStatus.choices)
    g1_available_kg = _kilograms()
    g2_available_kg = _kilograms()
    sold_kg = _kilograms()


class LotHistorySerializer(serializers.Serializer):
    lot = LotHistoryLotSerializer()
    origin = LotHistoryOriginSerializer(source="lot")
    stages = serializers.ListField(child=LotHistoryStageField())
    current = LotHistoryCurrentSerializer()
