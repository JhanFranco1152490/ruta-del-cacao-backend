import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_name
from apps.common.validators import validate_positive_area


class Plot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Una parcela no cambia de finca: lo que se registre después en ella (lotes, cosechas)
    # quedaría atribuido a otra finca.
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.PROTECT,
        related_name="plots",
    )
    code = models.CharField(max_length=50)
    code_normalized = models.CharField(max_length=200, editable=False)
    # El área declarada es la que cuenta para no superar el área de la finca, tenga o no
    # contorno dibujado.
    area_hectares = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_positive_area],
    )
    # Vértices en orden, sin repetir el primero al final. Las coordenadas se guardan como texto
    # con 7 decimales para que el JSON no les cambie la precisión.
    boundary = models.JSONField(null=True, blank=True)
    # La calcula el servidor a partir de `boundary`; nunca la envía el cliente.
    measured_area_hectares = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    # Hora del dispositivo, solo informativa (ver `Farm.captured_at`).
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["farm", "code_normalized"],
                name="plots_farm_code_normalized_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(area_hectares__gt=0),
                name="plots_area_hectares_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(boundary__isnull=True, measured_area_hectares__isnull=True)
                    | models.Q(boundary__isnull=False, measured_area_hectares__isnull=False)
                ),
                name="plots_boundary_with_measured_area",
            ),
        ]
        # Una parcela se desactiva, nunca se borra: lo que se registre en ella depende de que
        # siga existiendo.
        default_permissions = ()
        permissions = [
            ("view_plot", "Puede consultar parcelas"),
            ("add_plot", "Puede registrar parcelas"),
            ("change_plot", "Puede editar, activar y desactivar parcelas"),
        ]

    def clean(self):
        if isinstance(self.code, str):
            self.code = self.code.strip()
        if not self.code:
            raise ValidationError({"code": "Este campo es obligatorio."})
        self.code_normalized = normalize_name(self.code)


class PlotAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Parcela creada"
        UPDATED = "updated", "Parcela actualizada"
        STATUS_CHANGED = "status_changed", "Estado de parcela modificado"

    plot = models.ForeignKey(
        Plot,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="plot_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # Las dos áreas de la parcela tras el cambio: así queda en el historial cuánto difería la
    # declarada de la dibujada cada vez que se aceptó.
    area_hectares = models.DecimalField(max_digits=10, decimal_places=2)
    measured_area_hectares = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
    )
