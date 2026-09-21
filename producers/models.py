import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models
from .contacts import InvalidPhoneNumber, normalize_phone

from .documents import InvalidIdentityDocument, normalize_document_type, normalize_identity_document


class Producer(models.Model):
    class DocumentType(models.TextChoices):
        CC = "CC", "C?dula de ciudadan?a"
        CE = "CE", "C?dula de extranjer?a"
        PPT = "PPT", "Permiso por Protecci?n Temporal"
        NIT = "NIT", "N?mero de Identificaci?n Tributaria"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member_code = models.CharField(max_length=11, unique=True, editable=False)
    document_type = models.CharField(max_length=3, choices=DocumentType.choices)
    identity_document = models.CharField(max_length=30)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=25, null=True, blank=True)
    email = models.EmailField(max_length=254, null=True, blank=True)
    municipality_code = models.CharField(max_length=20)
    joined_on = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "identity_document"],
                name="producers_document_type_number_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "municipality_code"]),
            models.Index(fields=["last_name", "first_name", "id"]),
        ]
        permissions = [
            ("view", "Puede consultar productores"),
            ("create", "Puede crear productores"),
            ("update", "Puede actualizar productores"),
            ("change_status", "Puede cambiar el estado de productores"),
        ]
        ordering = ["last_name", "first_name", "id"]

    def clean_fields(self, exclude=None):
        if isinstance(self.email, str):
            self.email = self.email.strip().lower() or None
        if isinstance(self.phone, str):
         self.phone = self.phone.strip() or None
        super().clean_fields(exclude=exclude)

    def clean(self):
        errors = {}

        try:
            self.document_type = normalize_document_type(self.document_type)
        except (AttributeError, InvalidIdentityDocument):
            errors["document_type"] = "El tipo de documento no es v?lido."

        try:
            self.identity_document = normalize_identity_document(self.identity_document)
        except (AttributeError, InvalidIdentityDocument):
            errors["identity_document"] = "El n?mero de documento no es v?lido."

        for field_name in ("first_name", "last_name", "municipality_code"):
            value = getattr(self, field_name)
            normalized = value.strip() if isinstance(value, str) else ""
            setattr(self, field_name, normalized)
            if not normalized:
                errors[field_name] = "Este campo es obligatorio."

        try:
            self.phone = normalize_phone(self.phone)
        except InvalidPhoneNumber:
            errors["phone"] = "El teléfono debe contener solo entre 7 y 10 dígitos."

        self.email = self.email.strip().lower() if isinstance(self.email, str) else self.email
        if self.email == "":
            self.email = None
        elif self.email:
            try:
                validate_email(self.email)
            except ValidationError:
                errors["email"] = "El correo electr?nico no es v?lido."

        if self.joined_on and self.joined_on > datetime.now(ZoneInfo("America/Bogota")).date():
            errors["joined_on"] = "La fecha de vinculaci?n no puede ser futura."

        if self.version < 1:
            errors["version"] = "La versi?n debe ser un entero positivo."

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.member_code} ? {self.first_name} {self.last_name}"
