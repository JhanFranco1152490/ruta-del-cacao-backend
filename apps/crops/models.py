import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.audit import AuditEventBase

from .choices import ManagementSystem, ShadeType, Stage
from .text import normalize_variety_name


class CacaoVariety(models.Model):
    """El catálogo común de variedades: la asociación lo administra y el productor escoge de
    él, para que los reportes no cuenten `CCN51` y `CCN-51` por separado."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=60)
    name_normalized = models.CharField(max_length=120, editable=False)
    description = models.CharField(max_length=200, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name_normalized"]
        constraints = [
            models.UniqueConstraint(
                fields=["name_normalized"],
                name="crops_variety_name_normalized_unique",
            ),
        ]
        default_permissions = ()
        permissions = [
            (
                "manage_cacaovariety",
                "Puede registrar, editar, activar y desactivar variedades de cacao",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.name_normalized = normalize_variety_name(self.name or "")
        # Un nombre hecho solo de espacios o guiones quedaría vacío al compararlo.
        if not self.name_normalized:
            raise ValidationError({"name": "Este campo es obligatorio."})


class PlotCharacterization(models.Model):
    """La ficha agronómica vigente de una parcela. Hay una sola por parcela y su identidad es la
    de la parcela; lo que fue cambiando queda en su historial, con los valores de cada versión."""

    # No se elimina: una parcela con ficha se desactiva en lugar de eliminarse.
    plot = models.OneToOneField(
        "plots.Plot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="characterization",
    )
    # Mes y año de la siembra principal; se guarda en el día 1. La edad no se guarda porque
    # cambia con el tiempo.
    planting_date = models.DateField()
    stage = models.CharField(max_length=32, choices=Stage.choices)
    management_system = models.CharField(
        max_length=32, choices=ManagementSystem.choices, null=True, blank=True
    )
    shade_type = models.CharField(max_length=32, choices=ShadeType.choices, null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    # Hora del dispositivo, solo informativa: el orden y los conflictos se deciden con `version`.
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(planting_date__day=1),
                name="crops_planting_date_first_of_month",
            ),
        ]
        default_permissions = ()
        permissions = [
            (
                "change_plotcharacterization",
                "Puede registrar y editar la caracterización de parcelas",
            ),
        ]


class PlotCharacterizationVariety(models.Model):
    """Una variedad sembrada en la parcela y cuántos árboles tiene. Se cuentan árboles y no
    porcentajes porque es lo que el productor cuenta en campo."""

    characterization = models.ForeignKey(
        PlotCharacterization,
        on_delete=models.CASCADE,
        related_name="varieties",
    )
    variety = models.ForeignKey(
        CacaoVariety,
        on_delete=models.PROTECT,
        related_name="characterization_rows",
    )
    tree_count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["characterization", "variety"],
                name="crops_characterization_variety_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(tree_count__gt=0),
                name="crops_tree_count_positive",
            ),
        ]
        default_permissions = ()


class PlotCharacterizationAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Caracterización registrada"
        UPDATED = "updated", "Caracterización actualizada"

    # Apunta a la parcela, que es la identidad de la ficha.
    plot = models.ForeignKey(
        "plots.Plot",
        on_delete=models.PROTECT,
        related_name="characterization_audit_events",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="plot_characterization_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # A diferencia de otros historiales, guarda los valores de la ficha tras el cambio: no tiene
    # datos personales, y sin ellos el historial no serviría para seguir el ciclo productivo
    # (cuándo pasó de una etapa a otra o cuándo se renovó).
    snapshot = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()


class CacaoVarietyAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Variedad registrada"
        UPDATED = "updated", "Variedad actualizada"
        STATUS_CHANGED = "status_changed", "Estado de variedad modificado"
        DELETED = "deleted", "Variedad eliminada"

    # El historial sobrevive a la variedad: una registrada por error se puede eliminar, y sus
    # eventos quedan sin la relación pero con la copia de `variety_ref` y `variety_name`.
    variety = models.ForeignKey(
        CacaoVariety,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    variety_ref = models.UUIDField(db_index=True)
    variety_name = models.CharField(max_length=60)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="cacao_variety_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
