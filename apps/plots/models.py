import uuid

from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.codes import format_code
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
    # Consecutivo de la parcela dentro de su finca, que asigna el servidor y nunca cambia.
    number = models.PositiveIntegerField(editable=False)
    # Nombre que le da el productor, opcional: se reconoce la parcela por él, pero la identifica
    # su código. Vacío se guarda como nulo para que varias parcelas sin nombre convivan.
    name = models.CharField(max_length=60, null=True, blank=True)
    name_normalized = models.CharField(max_length=200, editable=False, null=True)
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
                fields=["farm", "name_normalized"],
                name="plots_farm_name_normalized_unique",
            ),
            models.UniqueConstraint(
                fields=["farm", "number"],
                name="plots_farm_number_unique",
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
        # Se declaran a mano, con los mismos códigos que generaría Django, para que el productor
        # los lea en español al armar un rol para sus empleados. Eliminar es solo para lo creado
        # por error: lo que deja de usarse se desactiva.
        default_permissions = ()
        permissions = [
            ("view_plot", "Puede consultar parcelas"),
            ("add_plot", "Puede registrar parcelas"),
            ("change_plot", "Puede editar, activar y desactivar parcelas"),
            ("delete_plot", "Puede eliminar parcelas creadas por error"),
        ]

    @property
    def code(self) -> str:
        return format_code("P", self.number)

    def clean(self):
        if isinstance(self.name, str):
            self.name = self.name.strip() or None
        self.name_normalized = normalize_name(self.name) if self.name else None


class PlotAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Parcela creada"
        UPDATED = "updated", "Parcela actualizada"
        STATUS_CHANGED = "status_changed", "Estado de parcela modificado"
        DELETED = "deleted", "Parcela eliminada"

    # El historial sobrevive a la parcela y a quien actuó: al eliminar una parcela creada por
    # error, o una cuenta, sus eventos quedan sin la relación pero con la copia de `plot_ref` y
    # `plot_code`, que dice de qué parcela eran.
    plot = models.ForeignKey(
        Plot,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    plot_ref = models.UUIDField(db_index=True)
    plot_code = models.CharField(max_length=50)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
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
