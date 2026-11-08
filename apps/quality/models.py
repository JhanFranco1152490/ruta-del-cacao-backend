from decimal import Decimal

from django.db import models
from django.db.models.lookups import LessThanOrEqual

from apps.common.audit import AuditEventBase

from .choices import DiscardReason

ONE_DECIMAL = 1
MAX_PERCENT = Decimal("100")
NOTES_MAX_LENGTH = 500
DETAIL_MAX_LENGTH = 300


def _percent():
    return models.DecimalField(max_digits=4, decimal_places=ONE_DECIMAL)


def _kilograms():
    return models.DecimalField(max_digits=7, decimal_places=ONE_DECIMAL)


def _between(field, low, high):
    return models.Q(**{f"{field}__gte": low, f"{field}__lte": high})


def _reason(field):
    return models.CharField(max_length=24, choices=DiscardReason.choices, **field)


def _other_has_detail(reason, detail):
    # Con Otro, el detalle es lo único que dice por qué.
    return ~models.Q(**{reason: DiscardReason.OTHER}) | ~models.Q(**{detail: ""})


class QualityEvaluation(models.Model):
    """La prueba de corte de una muestra del lote seco: qué parte de los granos salió bien
    fermentada, con moho o con otros defectos. El resto (violetas, pizarrosos) no se pide, así que
    los tres suman como mucho 100. Un lote tiene una sola evaluación vigente."""

    lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="quality_evaluation",
    )
    well_fermented_pct = _percent()
    moldy_pct = _percent()
    other_defects_pct = _percent()
    notes = models.CharField(max_length=NOTES_MAX_LENGTH, blank=True, default="")
    # PROTECT: una cuenta que evaluó o corrigió un lote no se elimina.
    evaluated_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    evaluated_at = models.DateTimeField()
    corrected_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    corrected_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["evaluated_at"]
        constraints = [
            *(
                models.CheckConstraint(
                    condition=_between(field, 0, MAX_PERCENT),
                    name=f"quality_evaluation_{field}_range",
                )
                for field in ("well_fermented_pct", "moldy_pct", "other_defects_pct")
            ),
            models.CheckConstraint(
                condition=LessThanOrEqual(
                    models.F("well_fermented_pct")
                    + models.F("moldy_pct")
                    + models.F("other_defects_pct"),
                    MAX_PERCENT,
                ),
                name="quality_evaluation_total_at_most_100",
            ),
            models.CheckConstraint(
                condition=models.Q(corrected_by__isnull=True, corrected_at__isnull=True)
                | models.Q(corrected_by__isnull=False, corrected_at__isnull=False),
                name="quality_evaluation_correction_complete",
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados. Van todos aquí: son los de toda la app.
        default_permissions = ()
        permissions = [
            ("evaluate_lot", "Puede registrar y corregir la evaluación física de un lote"),
            ("classify_lot", "Puede clasificar lotes por calibre"),
            ("discard_lot", "Puede descartar lotes completos"),
        ]

    def __str__(self):
        return str(self.lot)


class LotClassification(models.Model):
    """El reparto del peso seco del lote entre G1, G2 y descarte. Que sumen el peso seco lo revisa
    el servicio: el peso está en el secado, en otra tabla."""

    lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="classification",
    )
    g1_kg = _kilograms()
    g2_kg = _kilograms()
    discard_kg = _kilograms()
    # Solo con descarte.
    discard_reason = _reason({"blank": True, "default": ""})
    discard_detail = models.CharField(max_length=DETAIL_MAX_LENGTH, blank=True, default="")
    classified_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    classified_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["classified_at"]
        default_permissions = ()
        constraints = [
            *(
                models.CheckConstraint(
                    condition=models.Q(**{f"{field}__gte": 0}),
                    name=f"quality_classification_{field}_not_negative",
                )
                for field in ("g1_kg", "g2_kg", "discard_kg")
            ),
            models.CheckConstraint(
                condition=models.Q(discard_kg=0, discard_reason="")
                | models.Q(discard_kg__gt=0, discard_reason__in=DiscardReason.values),
                name="quality_classification_reason_with_discard",
            ),
            models.CheckConstraint(
                condition=_other_has_detail("discard_reason", "discard_detail"),
                name="quality_classification_other_has_detail",
            ),
        ]

    def __str__(self):
        return str(self.lot)


class LotDiscard(models.Model):
    """El descarte del lote completo. Es irreversible: el lote no se clasifica, no entra a bodega
    ni se vende, pero conserva su historia."""

    lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="discard",
    )
    reason = _reason({})
    detail = models.CharField(max_length=DETAIL_MAX_LENGTH, blank=True, default="")
    discarded_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="+")
    discarded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["discarded_at"]
        default_permissions = ()
        constraints = [
            models.CheckConstraint(
                condition=models.Q(reason__in=DiscardReason.values),
                name="quality_discard_reason_choice",
            ),
            models.CheckConstraint(
                condition=_other_has_detail("reason", "detail"),
                name="quality_discard_other_has_detail",
            ),
        ]

    def __str__(self):
        return str(self.lot)


class QualityAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        EVALUATED = "evaluated", "Evaluación registrada"
        EVALUATION_CORRECTED = "evaluation_corrected", "Evaluación corregida"
        CLASSIFIED = "classified", "Lote clasificado"
        DISCARDED = "discarded", "Lote descartado"

    # Un lote Seco o posterior no se elimina, así que el historial apunta a él directamente.
    lot = models.ForeignKey(
        "lots.Lot",
        on_delete=models.PROTECT,
        related_name="quality_audit_events",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="quality_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión de la evaluación que dejó el cambio; la clasificación y el descarte no cambian.
    version = models.PositiveIntegerField()
    # Por cada campo, su valor anterior y nuevo con los textos de la API. No hay datos personales:
    # las cuentas se guardan por su id.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
