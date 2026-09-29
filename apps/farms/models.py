import uuid

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.territorial import (
    InvalidDepartmentCode,
    InvalidMunicipalityCode,
    MunicipalityDepartmentMismatch,
    get_department,
    get_municipality,
    validate_municipality_department,
)

from .validators import (
    normalize_farm_name,
    validate_altitude,
    validate_latitude,
    validate_longitude,
    validate_positive_area,
)


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
        # Una finca se desactiva, nunca se borra: conserva su historial y lo que dependa de ella.
        default_permissions = ("view", "add", "change")

    def clean(self):
        errors = {}

        if isinstance(self.name, str):
            self.name = self.name.strip()
        if self.name:
            self.name_normalized = normalize_farm_name(self.name)
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
                errors["municipality_code"] = "El municipio no pertenece al departamento."

        if errors:
            raise ValidationError(errors)


class FarmAuditEvent(models.Model):
    class Action(models.TextChoices):
        CREATED = "created", "Finca creada"
        UPDATED = "updated", "Finca actualizada"
        STATUS_CHANGED = "status_changed", "Estado de finca modificado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    farm = models.ForeignKey(
        Farm,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="farm_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    changed_fields = models.JSONField(default=list, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
