import uuid

from django.db import models

from apps.common.audit import AuditEventBase

from .choices import LotStatus


class Lot(models.Model):
    """La unidad que se rastrea desde que entra al cajón hasta que se vende. Sale de una sola
    cosecha, completa: su peso es el de la cosecha y su origen es uno solo. De él cuelgan
    fermentación, secado, calidad, bodega y venta."""

    # Lo genera el dispositivo, para que un reenvío no cree otro lote.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Un lote por cosecha. Mientras exista el lote, la cosecha no se edita ni se elimina.
    harvest = models.OneToOneField(
        "harvests.Harvest",
        on_delete=models.PROTECT,
        related_name="lot",
    )
    # Único e inmutable: ningún servicio lo modifica. Se imprime y se escanea.
    code = models.CharField(max_length=40, unique=True, editable=False)
    status = models.CharField(
        max_length=16, choices=LotStatus.choices, default=LotStatus.GENERATED
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.code

    def advance_status(self, expected, new, *, actor):
        """Mueve el lote de `expected` a `new`. Lo llaman fermentación, secado y calidad dentro de
        su transacción, con la finca del lote ya bloqueada, por este método y sin importar esta
        app."""
        from .services.status import advance_lot_status

        return advance_lot_status(self, expected, new, actor=actor)

    class Meta:
        ordering = ["-created_at", "code"]
        indexes = [models.Index(fields=["status"], name="lots_status_idx")]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados. Eliminar es solo para un lote conformado por error.
        default_permissions = ()
        permissions = [
            ("view_lot", "Puede consultar lotes"),
            ("add_lot", "Puede conformar lotes"),
            ("delete_lot", "Puede eliminar lotes conformados por error"),
        ]


class LotQrCode(models.Model):
    """El código QR de un lote: un token aleatorio que abre su trazabilidad pública sin sesión. Uno
    por lote; no se edita, no se reemplaza y no se recicla, porque queda impreso en los sacos."""

    lot = models.OneToOneField(Lot, on_delete=models.PROTECT, related_name="qr_code")
    # Va en la dirección del QR en lugar del código del lote, que se adivina y lleva el código de
    # socio del productor.
    token = models.CharField(max_length=16, unique=True, editable=False)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.token

    class Meta:
        ordering = ["-created_at"]
        default_permissions = ()
        permissions = [("add_lotqrcode", "Puede generar el código QR de un lote")]


class LotCodeSequence(models.Model):
    """El último consecutivo de lote de una parcela en un día de cosecha. No baja al eliminar un
    lote: así el consecutivo no se recicla."""

    # Con una parcela con cosechas esta fila nunca se borra en cascada: la parcela no se elimina.
    plot = models.ForeignKey("plots.Plot", on_delete=models.CASCADE, related_name="+")
    harvest_date = models.DateField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["plot", "harvest_date"], name="lots_sequence_plot_date_unique"
            ),
        ]


class LotAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Lote conformado"
        STATUS_CHANGED = "status_changed", "Estado del lote modificado"
        DELETED = "deleted", "Lote eliminado"

    # El historial sobrevive al lote y a quien actuó: al eliminar un lote conformado por error,
    # sus eventos quedan sin la relación pero con la copia de `lot_ref`, `code` y `harvest_ref`.
    lot = models.ForeignKey(
        Lot,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    lot_ref = models.UUIDField(db_index=True)
    code = models.CharField(max_length=40)
    harvest_ref = models.UUIDField()
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="lot_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    version = models.PositiveIntegerField()
    # Para `status_changed`, el estado anterior y el nuevo.
    changes = models.JSONField(default=dict)

    # El productor del registro, copiado al registrar: el evento sigue en la bitácora aunque el
    # registro se elimine y su relación quede vacía.
    producer_ref = models.UUIDField(null=True, blank=True, editable=False)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
        indexes = [
            models.Index(fields=["producer_ref", "occurred_at"], name="lots_audit_producer_idx")
        ]
