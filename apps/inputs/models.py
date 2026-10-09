import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_catalog_name

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 80
PACKAGE_SIZE_MIN = Decimal("0.001")
PACKAGE_SIZE_MAX = Decimal("100000")


class AgriculturalInput(models.Model):
    """Un insumo del catálogo de un productor, compartido por todas sus fincas. La unidad es la
    de las cantidades que se registren con él; la presentación (empaque y contenido) solo ayuda a
    capturar y a mostrar esas cantidades."""

    class InputType(models.TextChoices):
        FERTILIZER = "fertilizer", "Fertilizante"
        ORGANIC_FERTILIZER = "organic_fertilizer", "Abono"
        FUNGICIDE = "fungicide", "Fungicida"
        INSECTICIDE = "insecticide", "Insecticida"
        OTHER = "other", "Otro"

    class Unit(models.TextChoices):
        KG = "kg", "Kilogramos"
        G = "g", "Gramos"
        L = "l", "Litros"
        ML = "ml", "Mililitros"
        UNIT = "unit", "Unidades"

    class PackageType(models.TextChoices):
        # Lista fija para que la interfaz sepa escribir el plural (potes, galones).
        SACK = "sack", "Bulto"
        BAG = "bag", "Bolsa"
        TUB = "tub", "Pote"
        FLASK = "flask", "Frasco"
        BOTTLE = "bottle", "Botella"
        GALLON = "gallon", "Galón"
        DRUM = "drum", "Caneca"
        BOX = "box", "Caja"
        SACHET = "sachet", "Sobre"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.PROTECT,
        related_name="agricultural_inputs",
    )
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    # Sin acotar a 80: la normalización de Unicode puede expandir algunos caracteres.
    name_normalized = models.CharField(max_length=240, editable=False)
    input_type = models.CharField(max_length=32, choices=InputType.choices)
    unit = models.CharField(max_length=8, choices=Unit.choices)
    # Cómo se compra el insumo (un pote de 100 mL): no cambia lo que se cuenta, que va en la
    # unidad. Los dos van juntos o ninguno.
    package_type = models.CharField(
        max_length=16, choices=PackageType.choices, null=True, blank=True
    )
    package_size = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        validators=[MinValueValidator(PACKAGE_SIZE_MIN), MaxValueValidator(PACKAGE_SIZE_MAX)],
    )
    is_active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name_normalized"]
        constraints = [
            models.UniqueConstraint(
                fields=["producer", "input_type", "name_normalized"],
                name="inputs_input_producer_type_name_unique",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(package_type__isnull=False, package_size__isnull=False)
                    | models.Q(package_type__isnull=True, package_size__isnull=True)
                ),
                name="inputs_input_package_both_or_none",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    package_size__gte=PACKAGE_SIZE_MIN, package_size__lte=PACKAGE_SIZE_MAX
                )
                | models.Q(package_size__isnull=True),
                name="inputs_input_package_size_range",
            ),
        ]
        default_permissions = ()
        permissions = [
            ("view_agriculturalinput", "Puede consultar insumos agrícolas"),
            ("add_agriculturalinput", "Puede registrar insumos agrícolas"),
            (
                "change_agriculturalinput",
                "Puede editar, activar y desactivar insumos agrícolas",
            ),
            (
                "delete_agriculturalinput",
                "Puede eliminar insumos agrícolas creados por error",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.name_normalized = normalize_catalog_name(self.name or "")
        # La longitud se revisa aquí y no en un validador del campo: ese correría antes de
        # recortar los espacios.
        if not self.name_normalized:
            errors["name"] = "Este campo es obligatorio."
        elif not NAME_MIN_LENGTH <= len(self.name) <= NAME_MAX_LENGTH:
            errors["name"] = (
                f"El nombre debe tener entre {NAME_MIN_LENGTH} y {NAME_MAX_LENGTH} caracteres."
            )
        if self.package_type is None and self.package_size is not None:
            errors["package_type"] = "El empaque es obligatorio si hay contenido."
        elif self.package_type is not None and self.package_size is None:
            errors["package_size"] = "El contenido es obligatorio si hay empaque."
        if errors:
            raise ValidationError(errors)


class AgriculturalInputAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Insumo registrado"
        UPDATED = "updated", "Insumo actualizado"
        STATUS_CHANGED = "status_changed", "Estado de insumo modificado"
        DELETED = "deleted", "Insumo eliminado"

    # El historial sobrevive al insumo: uno registrado por error se puede eliminar, y sus eventos
    # quedan sin la relación pero con la copia de `input_ref` y `input_name`.
    input = models.ForeignKey(
        AgriculturalInput,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    input_ref = models.UUIDField(db_index=True)
    input_name = models.CharField(max_length=NAME_MAX_LENGTH)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="agricultural_input_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión del insumo que dejó este cambio.
    version = models.PositiveIntegerField()
    # Por cada campo cambiado, su valor anterior y nuevo con los textos de la API. A diferencia de
    # otros historiales guarda valores: un insumo no tiene datos personales, y sin ellos no se
    # podría saber qué cambió ni de qué a qué.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
