import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.text import normalize_catalog_name

NAME_MAX_LENGTH = 40
MIN_CAPACITY_KG = 1
# Un cajón ronda los 300 a 1.000 kg de cacao en baba: el límite solo atrapa un cero de más.
MAX_CAPACITY_KG = 10_000


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
    capacity_kg = models.PositiveIntegerField(
        validators=[MinValueValidator(MIN_CAPACITY_KG), MaxValueValidator(MAX_CAPACITY_KG)]
    )
    is_active = models.BooleanField(default=True)
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
