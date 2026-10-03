import uuid

from django.db import models

from apps.common.choices import DocumentType
from apps.common.municipalities import validate_municipality_code
from apps.common.validators import validate_not_future, validate_phone, validate_producer_document

DOCUMENT_UNIQUE_CONSTRAINT = "producers_document_type_number_unique"
# Código del rol que identifica a la cuenta Productor (ver apps.accounts.system_roles). No se
# importa esa constante: esta app no importa de otra (ver AGENTS.md).
PRODUCER_ROLE_CODE = "producer"


class Producer(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member_code = models.CharField(max_length=11, unique=True, editable=False)
    document_type = models.CharField(max_length=3, choices=DocumentType.choices)
    identity_document = models.CharField(max_length=15, validators=[validate_producer_document])
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=25, null=True, blank=True, validators=[validate_phone])
    email = models.EmailField(max_length=254, null=True, blank=True)
    municipality_code = models.CharField(max_length=20, validators=[validate_municipality_code])
    joined_on = models.DateField(validators=[validate_not_future])
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document_type", "identity_document"],
                name=DOCUMENT_UNIQUE_CONSTRAINT,
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
            ("delete", "Puede eliminar productores creados por error"),
        ]
        ordering = ["last_name", "first_name", "id"]

    def __str__(self):
        return f"{self.member_code} — {self.first_name} {self.last_name}"
