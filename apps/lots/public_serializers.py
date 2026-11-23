"""Cómo se publica la trazabilidad pública de un lote.

Cada campo se declara aquí a mano, uno por uno: lo que no está en estas clases no sale, aunque la
historia del lote lo tenga. Agregar un dato a la página pública es una decisión, no un efecto de
cambiar la historia.
"""

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers

from .services.public import DATED_KINDS, SPAN_KINDS, PublicDatedStage


def _percent(**kwargs):
    return serializers.DecimalField(max_digits=4, decimal_places=1, **kwargs)


class PublicOriginSerializer(serializers.Serializer):
    farm = serializers.CharField()
    municipality = serializers.CharField()
    department = serializers.CharField()
    variety = serializers.CharField()


class PublicDatedStageSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=DATED_KINDS)
    date = serializers.DateField()


class PublicSpanStageSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SPAN_KINDS)
    started_on = serializers.DateField()
    ended_on = serializers.DateField(allow_null=True)
    days = serializers.IntegerField()


@extend_schema_field(
    PolymorphicProxySerializer(
        component_name="PublicLotStage",
        serializers={
            **{kind: PublicDatedStageSerializer for kind in DATED_KINDS},
            **{kind: PublicSpanStageSerializer for kind in SPAN_KINDS},
        },
        resource_type_field_name="kind",
    )
)
class PublicStageField(serializers.Field):
    def to_representation(self, stage):
        if isinstance(stage, PublicDatedStage):
            return PublicDatedStageSerializer(stage).data
        return PublicSpanStageSerializer(stage).data


class PublicQualitySerializer(serializers.Serializer):
    well_fermented_pct = _percent()
    g1_pct = _percent(allow_null=True)
    g2_pct = _percent(allow_null=True)
    discard_pct = _percent(allow_null=True)


class PublicLotTraceabilitySerializer(serializers.Serializer):
    origin = PublicOriginSerializer()
    stages = serializers.ListField(child=PublicStageField())
    quality = PublicQualitySerializer()
