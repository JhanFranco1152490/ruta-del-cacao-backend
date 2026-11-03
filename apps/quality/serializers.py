from rest_framework import serializers

from apps.common.serializers import full_name

from .choices import DiscardReason
from .models import ONE_DECIMAL, QualityEvaluation
from .services.queries import VIEWS

# Las opciones del estado del lote se toman de su campo por la relación, sin importar su app: así
# el esquema las reconoce como el mismo enum de los lotes.
LOT_STATUS_CHOICES = (
    QualityEvaluation._meta.get_field("lot").related_model._meta.get_field("status").choices
)


def _decimal(max_digits, **kwargs):
    return serializers.DecimalField(max_digits=max_digits, decimal_places=ONE_DECIMAL, **kwargs)


class QualityPersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return full_name(account)


class QualityLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.ChoiceField(choices=LOT_STATUS_CHOICES)
    # La que piden evaluar, clasificar y descartar en `expected_lot_version`.
    version = serializers.IntegerField()


class QualityFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class QualityEvaluationSerializer(serializers.Serializer):
    well_fermented_pct = _decimal(4)
    moldy_pct = _decimal(4)
    other_defects_pct = _decimal(4)
    notes = serializers.CharField()
    evaluated_at = serializers.DateTimeField()
    evaluated_by = QualityPersonSerializer()
    corrected_at = serializers.DateTimeField(allow_null=True)
    corrected_by = QualityPersonSerializer(allow_null=True)
    version = serializers.IntegerField()


class QualityClassificationSerializer(serializers.Serializer):
    g1_kg = _decimal(7)
    g2_kg = _decimal(7)
    discard_kg = _decimal(7)
    # Vacío sin descarte.
    discard_reason = serializers.ChoiceField(choices=DiscardReason.choices, allow_blank=True)
    discard_detail = serializers.CharField()
    classified_at = serializers.DateTimeField()
    classified_by = QualityPersonSerializer()


class QualityDiscardSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=DiscardReason.choices)
    detail = serializers.CharField()
    discarded_at = serializers.DateTimeField()
    discarded_by = QualityPersonSerializer()


# Un lote Seco o posterior, con lo que la pantalla de calidad necesita de su secado y lo que se
# registró de su calidad.
class LotQualitySerializer(serializers.Serializer):
    lot = QualityLotSerializer(source="*")
    farm = QualityFarmSerializer(source="harvest.plot.farm")
    # El peso seco es "el peso del lote" que reparte la clasificación.
    dry_weight_kg = _decimal(7, source="drying.dry_weight_kg")
    final_moisture_pct = _decimal(4, source="drying.final_moisture_pct")
    drying_ended_at = serializers.DateTimeField(source="drying.ended_at")
    evaluation = QualityEvaluationSerializer(source="quality_evaluation", allow_null=True)
    classification = QualityClassificationSerializer(allow_null=True)
    discard = QualityDiscardSerializer(allow_null=True)


class QualityListQuerySerializer(serializers.Serializer):
    # Los filtros de la pantalla; `page` y `page_size` los lee la paginación.
    view = serializers.ChoiceField(choices=list(VIEWS), required=False)
    farm = serializers.UUIDField(required=False)
    search = serializers.CharField(required=False, allow_blank=True, max_length=40)
    producer = serializers.UUIDField(required=False)


class QualitySummaryQuerySerializer(QualityListQuerySerializer):
    # Los mismos filtros de la lista menos la vista: las cifras son de todas.
    def get_fields(self):
        fields = super().get_fields()
        fields.pop("view")
        return fields


class QualitySummarySerializer(serializers.Serializer):
    to_evaluate = serializers.IntegerField()
    to_evaluate_kg = serializers.DecimalField(max_digits=12, decimal_places=ONE_DECIMAL)
    evaluated = serializers.IntegerField()
    discarded_this_month = serializers.IntegerField()
