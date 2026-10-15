import uuid

from django.db import models
from django.db.models import Q

from ..choices import ControlMethod, SamplingMethod, SamplingUnit
from .catalog import PestDisease


class PhytosanitaryMonitoring(models.Model):
    """El resultado de un monitoreo realizado: qué se contó y cuánto, y lo que no cabe en números.

    La actividad es de la app de actividades y no cambia de columnas: este registro cuelga de ella
    y lleva su mismo `id`. Una vez registrado no se corrige: si hubo un error, se programa otro
    monitoreo.
    """

    activity = models.OneToOneField(
        "activities.AgriculturalActivity",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="phytosanitary_monitoring",
    )
    sampling_unit = models.CharField(max_length=8, choices=SamplingUnit.choices)
    evaluated_units = models.PositiveIntegerField()
    sampling_method = models.CharField(
        max_length=16, choices=SamplingMethod.choices, null=True, blank=True
    )
    notes = models.CharField(max_length=500, null=True, blank=True)
    # Sin plagas ni enfermedades: el monitoreo queda sin detecciones.
    no_presence = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(evaluated_units__gt=0), name="health_monitoring_units_positive"
            ),
            models.CheckConstraint(
                condition=Q(sampling_unit__in=SamplingUnit.values),
                name="health_monitoring_sampling_unit_valid",
            ),
        ]
        default_permissions = ()


class Detection(models.Model):
    """Una plaga o enfermedad encontrada en un monitoreo, con cuántas unidades afectó."""

    # Lo genera el dispositivo: desde una detección que todavía está en la cola sin conexión se
    # puede programar el control que la atiende.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    monitoring = models.ForeignKey(
        PhytosanitaryMonitoring, on_delete=models.CASCADE, related_name="detections"
    )
    # Una plaga usada en algún monitoreo no se elimina del catálogo: se desactiva.
    pest_disease = models.ForeignKey(
        PestDisease,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detections",
    )
    # Lo que escribió el capataz al elegir "Otra", cuando no está en el catálogo.
    other_description = models.CharField(max_length=100, null=True, blank=True)
    # "Otra" comparada como los nombres del catálogo, para no repetirla en el mismo monitoreo.
    normalized_other = models.CharField(max_length=200, null=True, blank=True, editable=False)
    affected_units = models.PositiveIntegerField()
    # Unidades afectadas ÷ evaluadas × 100. Se guarda y no se calcula al leer: es lo que vio el
    # capataz al registrarlo, y el historial la filtra y la compara.
    incidence = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        ordering = ["monitoring", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(
                        pest_disease__isnull=False,
                        other_description__isnull=True,
                        normalized_other__isnull=True,
                    )
                    | (
                        Q(
                            pest_disease__isnull=True,
                            other_description__isnull=False,
                            normalized_other__isnull=False,
                        )
                        & ~Q(other_description="")
                        & ~Q(normalized_other="")
                    )
                ),
                name="health_detection_catalog_or_other",
            ),
            models.UniqueConstraint(
                fields=["monitoring", "pest_disease"], name="health_detection_pest_once"
            ),
            models.UniqueConstraint(
                fields=["monitoring", "normalized_other"], name="health_detection_other_once"
            ),
            models.CheckConstraint(
                condition=Q(affected_units__gt=0), name="health_detection_units_positive"
            ),
            models.CheckConstraint(
                condition=Q(incidence__gte=0, incidence__lte=100),
                name="health_detection_incidence_percentage",
            ),
        ]
        default_permissions = ()


class PhytosanitaryTreatment(models.Model):
    """El vínculo de un control fitosanitario con la detección que atiende.

    El control es una actividad: así aparece en el calendario, recibe alertas y descuenta los
    insumos que gastó con lo que ya existe. Aquí solo va lo que lo hace un control: a qué
    detección responde y qué se hizo o se piensa hacer. Una detección puede tener varios, por
    ejemplo aplicaciones sucesivas.
    """

    activity = models.OneToOneField(
        "activities.AgriculturalActivity",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="phytosanitary_treatment",
    )
    # Un monitoreo con controles no pierde sus detecciones: el control quedaría atendiendo algo
    # que no existe.
    detection = models.ForeignKey(Detection, on_delete=models.PROTECT, related_name="treatments")
    # Una referencia para quien lo aplique: no descuenta nada. Lo que se descuenta es lo que se
    # registra al realizarlo.
    planned_input = models.ForeignKey(
        "inputs.AgriculturalInput",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="planned_treatments",
    )
    # Obligatorio en un control realizado, lo exige el servicio; en uno programado es lo que se
    # piensa hacer, si ya se sabe.
    method = models.CharField(max_length=24, choices=ControlMethod.choices, null=True, blank=True)
    method_description = models.CharField(max_length=80, null=True, blank=True)

    class Meta:
        constraints = [
            # Cada rama pregunta primero si hay método: con `method` nulo, comparar contra
            # "other" da desconocido en SQL, y un CHECK desconocido deja pasar la fila.
            models.CheckConstraint(
                condition=(
                    (
                        Q(
                            method__isnull=False,
                            method=ControlMethod.OTHER,
                            method_description__isnull=False,
                        )
                        & ~Q(method_description="")
                    )
                    | (
                        Q(method__isnull=False, method_description__isnull=True)
                        & ~Q(method=ControlMethod.OTHER)
                    )
                    | Q(method__isnull=True, method_description__isnull=True)
                ),
                name="health_treatment_description_only_with_other",
            ),
        ]
        default_permissions = ()
