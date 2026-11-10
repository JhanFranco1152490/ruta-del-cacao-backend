import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.common.audit import AuditEventBase
from apps.common.choices import DocumentType
from apps.common.validators import validate_phone, validate_producer_document

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 120
CONTACT_REQUIRED_MESSAGE = "Escribe un teléfono o un correo."
DOCUMENT_UNIQUE_CONSTRAINT = "buyers_buyer_producer_document_unique"
CONTACT_REQUIRED_CONSTRAINT = "buyers_buyer_phone_or_email"


class Buyer(models.Model):
    """Un comprador del cacao de un productor. Es de todo el productor, no de una finca. Lo
    identifica su documento: dos compradores pueden llamarse igual."""

    class BuyerType(models.TextChoices):
        CHOCOLATE_INDUSTRY = "chocolate_industry", "Industria chocolatera"
        EXPORTER = "exporter", "Exportador"
        INTERMEDIARY = "intermediary", "Intermediario o acopiador"
        COOPERATIVE = "cooperative", "Cooperativa o asociación"
        ARTISAN_PROCESSOR = "artisan_processor", "Transformador artesanal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    producer = models.ForeignKey(
        "producers.Producer", on_delete=models.PROTECT, related_name="buyers"
    )
    name = models.CharField(max_length=NAME_MAX_LENGTH)
    document_type = models.CharField(max_length=3, choices=DocumentType.choices)
    # Texto para conservar los ceros iniciales.
    identity_document = models.CharField(max_length=15, validators=[validate_producer_document])
    buyer_type = models.CharField(max_length=32, choices=BuyerType.choices)
    contact_name = models.CharField(max_length=NAME_MAX_LENGTH, null=True, blank=True)
    phone = models.CharField(max_length=10, null=True, blank=True, validators=[validate_phone])
    email = models.EmailField(max_length=254, null=True, blank=True)
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
        ordering = [Lower("name"), "id"]
        constraints = [
            # También entre inactivos: activar uno no puede chocar con otro registrado después.
            models.UniqueConstraint(
                fields=["producer", "document_type", "identity_document"],
                name=DOCUMENT_UNIQUE_CONSTRAINT,
            ),
            models.CheckConstraint(
                condition=models.Q(phone__isnull=False) | models.Q(email__isnull=False),
                name=CONTACT_REQUIRED_CONSTRAINT,
            ),
        ]
        default_permissions = ()
        permissions = [
            ("view_buyer", "Puede consultar compradores"),
            ("add_buyer", "Puede registrar compradores"),
            ("change_buyer", "Puede editar, activar y desactivar compradores"),
            ("delete_buyer", "Puede eliminar compradores creados por error"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        errors = {}
        self.name = _trimmed(self.name) or ""
        self.contact_name = _trimmed(self.contact_name)
        self.phone = _trimmed(self.phone)
        email = _trimmed(self.email)
        self.email = email.lower() if email else None
        # Las longitudes se revisan aquí y no en un validador del campo: ese correría antes de
        # recortar los espacios.
        if not self.name:
            errors["name"] = "Este campo es obligatorio."
        elif not NAME_MIN_LENGTH <= len(self.name) <= NAME_MAX_LENGTH:
            errors["name"] = _length_message("nombre")
        if self.contact_name and not NAME_MIN_LENGTH <= len(self.contact_name) <= NAME_MAX_LENGTH:
            errors["contact_name"] = _length_message("nombre de contacto")
        if self.phone is None and self.email is None:
            errors["phone"] = errors["email"] = CONTACT_REQUIRED_MESSAGE
        if errors:
            raise ValidationError(errors)


def _trimmed(value: str | None) -> str | None:
    if not isinstance(value, str):
        return value
    return value.strip() or None


def _length_message(label: str) -> str:
    return f"El {label} debe tener entre {NAME_MIN_LENGTH} y {NAME_MAX_LENGTH} caracteres."


class BuyerAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Comprador registrado"
        UPDATED = "updated", "Comprador actualizado"
        STATUS_CHANGED = "status_changed", "Estado de comprador modificado"
        DELETED = "deleted", "Comprador eliminado"

    # El historial sobrevive al comprador: uno registrado por error se puede eliminar, y sus
    # eventos quedan sin la relación pero con la copia de `buyer_ref`. Solo se guardan los nombres
    # de los campos que cambiaron, nunca sus valores ni el nombre del comprador: puede ser una
    # persona natural, con su cédula, su teléfono y su correo.
    buyer = models.ForeignKey(
        Buyer,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    buyer_ref = models.UUIDField(db_index=True)
    buyer_type = models.CharField(max_length=32, choices=Buyer.BuyerType.choices)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión del comprador que dejó este cambio.
    version = models.PositiveIntegerField()

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
