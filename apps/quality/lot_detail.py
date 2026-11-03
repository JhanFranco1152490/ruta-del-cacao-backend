from types import SimpleNamespace

from rest_framework import serializers

from .choices import DiscardReason
from .models import ONE_DECIMAL


def _decimal(max_digits, **kwargs):
    return serializers.DecimalField(max_digits=max_digits, decimal_places=ONE_DECIMAL, **kwargs)


# Lo que calidad agrega a la representación de un lote: la evaluación y, al cerrarla, los kilos
# de G1 y G2 (que bodega toma como máximos) o el descarte completo. Nulo mientras el lote no tenga
# evaluación.
class LotQualityDetailSerializer(serializers.Serializer):
    well_fermented_pct = _decimal(4)
    moldy_pct = _decimal(4)
    other_defects_pct = _decimal(4)
    evaluated_at = serializers.DateTimeField()
    # Nulos hasta clasificar, y también con el lote descartado completo.
    g1_kg = _decimal(7, allow_null=True)
    g2_kg = _decimal(7, allow_null=True)
    discard_kg = _decimal(7, allow_null=True)
    # El de la parte descartada al clasificar o el del lote completo.
    discard_reason = serializers.ChoiceField(choices=DiscardReason.choices, allow_null=True)
    discarded_at = serializers.DateTimeField(allow_null=True)

    def to_representation(self, lot):
        evaluation = getattr(lot, "quality_evaluation", None)
        if evaluation is None:
            return None
        classification = getattr(lot, "classification", None)
        discard = getattr(lot, "discard", None)
        if classification is not None:
            discard_reason = classification.discard_reason or None
        else:
            discard_reason = discard.reason if discard is not None else None
        return super().to_representation(
            SimpleNamespace(
                well_fermented_pct=evaluation.well_fermented_pct,
                moldy_pct=evaluation.moldy_pct,
                other_defects_pct=evaluation.other_defects_pct,
                evaluated_at=evaluation.evaluated_at,
                g1_kg=getattr(classification, "g1_kg", None),
                g2_kg=getattr(classification, "g2_kg", None),
                discard_kg=getattr(classification, "discard_kg", None),
                discard_reason=discard_reason,
                discarded_at=getattr(discard, "discarded_at", None),
            )
        )
