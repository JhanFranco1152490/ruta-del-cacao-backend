import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_catalog_name

NAME_MAX_LENGTH = 40
# Un decimal, como el peso de la cosecha en la báscula: así la capacidad se compara con el lote sin
# redondear.
CAPACITY_DECIMAL_PLACES = 1
MIN_CAPACITY_KG = Decimal("0.1")
# Un cajón ronda los 300 a 1.000 kg de cacao en baba: el límite solo atrapa un cero de más.
MAX_CAPACITY_KG = Decimal("10000")
OCCUPIED_IS_ACTIVE_CONSTRAINT = "facilities_facility_occupied_is_active"


class PostharvestFacility(models.Model):
    """Un cajón de fermentación o una marquesina de secado de una finca. La capacidad va en kg de
    cacao en baba, el mismo peso que trae un lote de su cosecha."""

    class FacilityType(models.TextChoices):
        FERMENTATION_BOX = "fermentation_box", "Cajón"
        SOLAR_DRYER = "solar_dryer", "Marquesina"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        "farms.Farm",
        on_delete=models.PROTECT,
        related_name="postharvest_facilities",
    )
    facility_type = models.CharField(max_length=32, choices=FacilityType.choices)
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    # Sin acotar a 40: la normalización de Unicode puede expandir algunos caracteres.
    name_normalized = models.CharField(max_length=120, editable=False)
    capacity_kg = models.DecimalField(
        max_digits=6,
        decimal_places=CAPACITY_DECIMAL_PLACES,
        validators=[MinValueValidator(MIN_CAPACITY_KG), MaxValueValidator(MAX_CAPACITY_KG)],
    )
    is_active = models.BooleanField(default=True)
    # El lote que está adentro, fermentando o secándose. Solo lo cambian `occupy` y `release`.
    # Uno a uno: un lote ocupa un solo elemento a la vez. PROTECT: un lote adentro no se borra.
    current_lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="occupied_facility",
    )
    occupied_since = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["facility_type", "name_normalized", "id"]
        constraints = [
            # Sin el tipo: un cajón y una marquesina con el mismo nombre en la misma finca no se
            # distinguirían en un aviso.
            models.UniqueConstraint(
                fields=["farm", "name_normalized"],
                name="facilities_facility_farm_name_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    capacity_kg__gte=MIN_CAPACITY_KG, capacity_kg__lte=MAX_CAPACITY_KG
                ),
                name="facilities_facility_capacity_range",
            ),
            models.CheckConstraint(
                condition=models.Q(current_lot__isnull=True, occupied_since__isnull=True)
                | models.Q(current_lot__isnull=False, occupied_since__isnull=False),
                name="facilities_facility_occupancy_both_or_none",
            ),
            # Así un desactivar y un ocupar que se cruzan nunca dejan un elemento inactivo con un
            # lote adentro, aunque cada uno haya leído el elemento libre y activo.
            models.CheckConstraint(
                condition=models.Q(current_lot__isnull=True) | models.Q(is_active=True),
                name=OCCUPIED_IS_ACTIVE_CONSTRAINT,
            ),
        ]
        indexes = [
            models.Index(fields=["farm", "facility_type"], name="facilities_farm_type_idx"),
        ]
        default_permissions = ()
        permissions = [
            ("view_postharvestfacility", "Puede consultar cajones y marquesinas"),
            ("add_postharvestfacility", "Puede registrar cajones y marquesinas"),
            (
                "change_postharvestfacility",
                "Puede editar, activar y desactivar cajones y marquesinas",
            ),
            (
                "delete_postharvestfacility",
                "Puede eliminar cajones y marquesinas creados por error",
            ),
        ]

    def __str__(self):
        return self.name

    def occupy(self, lot, *, kind, actor):
        """Deja `lot` adentro de este elemento. Lo llaman fermentación (con un cajón) y secado
        (con una marquesina) al iniciar, dentro de su transacción y con la finca del lote ya
        bloqueada. Otras apps lo usan por la relación de su propia clave foránea, sin importar
        esta. No revisa permisos: los pide el proceso que lo llama."""
        from .services.occupancy import occupy_facility

        return occupy_facility(self, lot, kind=kind, actor=actor)

    def release(self, lot, *, actor):
        """Deja el elemento libre al finalizar el proceso de `lot`, que debe ser el que está
        adentro."""
        from .services.occupancy import release_facility

        return release_facility(self, lot, actor=actor)

    def clean(self):
        if isinstance(self.name, str):
            self.name = self.name.strip()
        self.name_normalized = normalize_catalog_name(self.name or "")
        # La longitud se revisa aquí y no en un validador del campo: ese correría antes de
        # recortar los espacios.
        if not self.name_normalized:
            raise ValidationError({"name": "Este campo es obligatorio."})
        if len(self.name) > NAME_MAX_LENGTH:
            raise ValidationError(
                {"name": f"El nombre debe tener máximo {NAME_MAX_LENGTH} caracteres."}
            )


class PostharvestFacilityAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Elemento registrado"
        UPDATED = "updated", "Elemento actualizado"
        STATUS_CHANGED = "status_changed", "Estado de elemento modificado"
        OCCUPIED = "occupied", "Elemento ocupado por un lote"
        RELEASED = "released", "Elemento liberado"
        DELETED = "deleted", "Elemento eliminado"

    # El historial sobrevive al elemento: uno registrado por error se puede eliminar, y sus
    # eventos quedan sin la relación pero con la copia de su id, su nombre y su finca.
    facility = models.ForeignKey(
        PostharvestFacility,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    facility_ref = models.UUIDField(db_index=True)
    facility_name = models.CharField(max_length=NAME_MAX_LENGTH)
    farm_ref = models.UUIDField(db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="postharvest_facility_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión del elemento que dejó este cambio.
    version = models.PositiveIntegerField()
    # Por cada campo cambiado, su valor anterior y nuevo con los textos de la API. Un cajón no
    # tiene datos personales, así que se guardan los valores, como en los insumos.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
