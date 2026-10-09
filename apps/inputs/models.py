import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_catalog_name

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 80
BAG_WEIGHT_MIN = Decimal("1")
BAG_WEIGHT_MAX = Decimal("100")


class AgriculturalInput(models.Model):
    """Un insumo del catálogo de un productor, compartido por todas sus fincas. La unidad es la
    de las cantidades que se registren con él; un bulto lleva además su peso, porque cambia según
    el producto y sin él las cantidades en bultos no se podrían comparar ni sumar."""

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
        BAG = "bag", "Bulto"
        UNIT = "unit", "Unidades"

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
    bag_weight_kg = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(BAG_WEIGHT_MIN), MaxValueValidator(BAG_WEIGHT_MAX)],
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
                    models.Q(unit="bag", bag_weight_kg__isnull=False)
                    | (~models.Q(unit="bag") & models.Q(bag_weight_kg__isnull=True))
                ),
                name="inputs_input_bag_weight_iff_bag",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    bag_weight_kg__gte=BAG_WEIGHT_MIN, bag_weight_kg__lte=BAG_WEIGHT_MAX
                )
                | models.Q(bag_weight_kg__isnull=True),
                name="inputs_input_bag_weight_range",
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
        if self.unit == self.Unit.BAG and self.bag_weight_kg is None:
            errors["bag_weight_kg"] = "El peso del bulto es obligatorio."
        elif self.unit != self.Unit.BAG and self.bag_weight_kg is not None:
            errors["bag_weight_kg"] = "Solo un bulto lleva peso."
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
