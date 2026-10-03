import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.audit import AuditEventBase
from apps.common.municipality_altitude import altitude_range_for
from apps.common.territorial import (
    InvalidDepartmentCode,
    InvalidMunicipalityCode,
    MunicipalityDepartmentMismatch,
    get_department,
    get_municipality,
    validate_municipality_department,
)
from apps.common.text import normalize_name
from apps.common.validators import validate_latitude, validate_longitude, validate_positive_area

from .validators import validate_altitude

# Código del error de `clean()` cuando el municipio no es del departamento: el servicio lo
# reconoce por él para responderlo como un caso de negocio y no como un error de campo.
MUNICIPALITY_DEPARTMENT_MISMATCH = "municipality_department_mismatch"


class Farm(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.PROTECT,
        related_name="farms",
    )
    name = models.CharField(max_length=200)
    name_normalized = models.CharField(max_length=200, editable=False)
    department_code = models.CharField(max_length=2)
    municipality_code = models.CharField(max_length=5)
    details = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    area_hectares = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_positive_area],
    )
    altitude_masl = models.IntegerField(validators=[validate_altitude])
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=7,
        validators=[validate_latitude],
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        validators=[validate_longitude],
    )
    version = models.PositiveIntegerField(default=1)
    # Hora del dispositivo al registrar la finca, quizá sin conexión. Solo informativa: el reloj
    # del dispositivo no es confiable, así que el orden y los conflictos nunca dependen de ella
    # sino de `version` y de `created_at`, que es la hora en que el servidor la recibió.
    captured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["producer", "name_normalized"],
                name="farms_producer_name_normalized_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(area_hectares__gt=0),
                name="farms_area_hectares_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="farms_latitude_in_range",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name="farms_longitude_in_range",
            ),
        ]
        # Se declaran a mano, con los mismos códigos que generaría Django, para que el productor
        # los lea en español al armar un rol para sus empleados. Eliminar existe solo para fincas
        # creadas por error, sin registros del negocio; las demás se desactivan.
        default_permissions = ()
        permissions = [
            ("view_farm", "Puede consultar fincas"),
            ("add_farm", "Puede registrar fincas"),
            ("change_farm", "Puede editar, activar y desactivar fincas"),
            ("delete_farm", "Puede eliminar fincas creadas por error"),
        ]

    def clean(self):
        errors = {}

        if isinstance(self.name, str):
            self.name = self.name.strip()
        if self.name:
            self.name_normalized = normalize_name(self.name)
        else:
            errors["name"] = "Este campo es obligatorio."

        if isinstance(self.department_code, str):
            self.department_code = self.department_code.strip()
        if isinstance(self.municipality_code, str):
            self.municipality_code = self.municipality_code.strip()

        try:
            get_department(self.department_code)
        except InvalidDepartmentCode:
            errors["department_code"] = "El departamento no es válido."

        try:
            get_municipality(self.municipality_code)
        except InvalidMunicipalityCode:
            errors["municipality_code"] = "El municipio no es válido."

        if "department_code" not in errors and "municipality_code" not in errors:
            try:
                validate_municipality_department(
                    self.municipality_code,
                    self.department_code,
                )
            except MunicipalityDepartmentMismatch:
                errors["municipality_code"] = ValidationError(
                    "El municipio no pertenece al departamento.",
                    code=MUNICIPALITY_DEPARTMENT_MISMATCH,
                )

        if "municipality_code" not in errors and isinstance(self.altitude_masl, int):
            # La altitud también tiene que caber en el terreno del municipio elegido.
            terrain = altitude_range_for(self.municipality_code)
            if terrain and not terrain[0] <= self.altitude_masl <= terrain[1]:
                errors.setdefault(
                    "altitude_masl",
                    f"La altitud no corresponde al municipio elegido: allí el terreno va de "
                    f"{terrain[0]} a {terrain[1]} m.",
                )

        if errors:
            raise ValidationError(errors)


class FarmAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Finca creada"
        UPDATED = "updated", "Finca actualizada"
        STATUS_CHANGED = "status_changed", "Estado de finca modificado"
        DELETED = "deleted", "Finca eliminada"

    # La auditoría sobrevive a la finca y a quien actuó: al eliminar una finca creada por error,
    # o una cuenta, sus eventos quedan sin la relación pero con la copia de `farm_ref` y
    # `farm_name`, que dice de qué finca eran.
    farm = models.ForeignKey(
        Farm,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    farm_ref = models.UUIDField(db_index=True)
    farm_name = models.CharField(max_length=200)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="farm_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
