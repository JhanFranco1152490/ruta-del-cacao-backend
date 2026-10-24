import uuid
from decimal import Decimal

from django.db import models

from apps.common.audit import AuditEventBase

TEMPERATURE_DECIMAL_PLACES = 1
# Una masa en fermentación anda entre 25 y 50 °C: el tope solo atrapa un error de digitación, como
# 450 en vez de 45,0.
MAX_TEMPERATURE_C = Decimal("80")
# Dos decimales, como los muestran los medidores de pH (4,85).
PH_DECIMAL_PLACES = 2
MAX_PH = Decimal("14")
NOTES_MAX_LENGTH = 500


class FermentationProcess(models.Model):
    """La fermentación de un lote en un cajón, desde que se inicia hasta que se finaliza. Un lote
    tiene a lo sumo una, y se identifica por él."""

    lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="fermentation",
    )
    # Queda guardado después de liberar el cajón: es el historial de uso del cajón.
    facility = models.ForeignKey(
        "facilities.PostharvestFacility",
        on_delete=models.PROTECT,
        related_name="fermentation_processes",
    )
    started_at = models.DateTimeField()
    # Se inició aunque el lote pesaba más de lo que cabe en el cajón, con la confirmación de quien
    # lo registró.
    over_capacity = models.BooleanField(default=False)
    # PROTECT: una cuenta que respondió por una fermentación no se elimina.
    responsible = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
    )
    ended_at = models.DateTimeField(null=True, blank=True)
    end_notes = models.CharField(max_length=NOTES_MAX_LENGTH, blank=True, default="")
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    finished_by = models.ForeignKey(
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
        ordering = ["started_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(ended_at__gt=models.F("started_at")),
                name="fermentation_process_ends_after_start",
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados.
        default_permissions = ()
        permissions = [
            ("log_turns", "Puede registrar, corregir y eliminar volteos"),
            ("manage_fermentation", "Puede iniciar y finalizar fermentaciones"),
        ]

    def __str__(self):
        return str(self.lot)


class FermentationTurn(models.Model):
    """Un volteo de la masa de cacao, con la temperatura y el pH que se midieron. Su número no se
    guarda: es su posición por hora entre los volteos de la fermentación, para que uno registrado
    sin conexión que llega tarde quede en su lugar."""

    # Lo genera el dispositivo, para que un reenvío desde la cola no cree otro volteo.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Una fermentación no se elimina: el CASCADE solo ordena el modelo.
    process = models.ForeignKey(
        FermentationProcess,
        on_delete=models.CASCADE,
        related_name="turns",
    )
    # Truncada al minuto: dos registros del mismo minuto son el mismo volteo.
    turned_at = models.DateTimeField()
    temperature_c = models.DecimalField(max_digits=3, decimal_places=TEMPERATURE_DECIMAL_PLACES)
    ph = models.DecimalField(max_digits=4, decimal_places=PH_DECIMAL_PLACES)
    notes = models.CharField(max_length=NOTES_MAX_LENGTH, blank=True, default="")
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # La hora del dispositivo al guardar, informativa.
    captured_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["turned_at"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["process", "turned_at"], name="fermentation_turn_process_time_unique"
            ),
            models.CheckConstraint(
                condition=models.Q(temperature_c__gt=0, temperature_c__lte=MAX_TEMPERATURE_C),
                name="fermentation_turn_temperature_range",
            ),
            models.CheckConstraint(
                condition=models.Q(ph__gte=0, ph__lte=MAX_PH),
                name="fermentation_turn_ph_range",
            ),
        ]

    def __str__(self):
        return f"{self.process} · {self.turned_at:%Y-%m-%d %H:%M}"


class FermentationProcessAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        STARTED = "started", "Fermentación iniciada"
        UPDATED = "updated", "Inicio corregido"
        FINISHED = "finished", "Fermentación finalizada"
        TURN_CREATED = "turn_created", "Volteo registrado"
        TURN_UPDATED = "turn_updated", "Volteo corregido"
        TURN_DELETED = "turn_deleted", "Volteo eliminado"

    # Una fermentación no se elimina, así que su historial apunta a ella directamente.
    process = models.ForeignKey(
        FermentationProcess,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    # El volteo de los eventos `turn_*`, por su id: un volteo eliminado deja su copia aquí.
    turn_ref = models.UUIDField(null=True, blank=True, db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="fermentation_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión de la fermentación o del volteo que dejó este cambio.
    version = models.PositiveIntegerField()
    # Por cada campo cambiado, su valor anterior y nuevo con los textos de la API. Una fermentación
    # no tiene datos personales: las cuentas se guardan por su id.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
