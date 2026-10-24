import uuid
from decimal import Decimal

from django.db import models

from apps.common.audit import AuditEventBase

ONE_DECIMAL = 1
MAX_PERCENT = Decimal("100")
MAX_DAY_HOURS = Decimal("24")
# Voltear el grano más de dos veces por hora en un día no ocurre: el tope atrapa un error de
# digitación, como 200 en vez de 2.
MAX_TURNS_PER_DAY = 48
MIN_TURN_FREQUENCY_HOURS = Decimal("0.5")
NOTES_MAX_LENGTH = 500
LOG_DATE_UNIQUE_CONSTRAINT = "drying_log_process_date_unique"

RESULT_FIELDS = ("ended_at", "final_moisture_pct", "dry_weight_kg", "yield_pct", "total_sun_hours")


def _percent(**kwargs):
    return models.DecimalField(max_digits=4, decimal_places=ONE_DECIMAL, **kwargs)


def _day_hours(**kwargs):
    return models.DecimalField(max_digits=3, decimal_places=ONE_DECIMAL, **kwargs)


def _between(field, low, high):
    return models.Q(**{f"{field}__gte": low, f"{field}__lte": high})


class Weather(models.TextChoices):
    SUNNY = "sunny", "Soleado"
    PARTLY_CLOUDY = "partly_cloudy", "Parcialmente nublado"
    CLOUDY = "cloudy", "Nublado"
    RAINY = "rainy", "Lluvioso"


class DryingProcess(models.Model):
    """El secado de un lote en una marquesina, desde que se inicia hasta que se finaliza con su
    rendimiento. Un lote tiene a lo sumo uno, y se identifica por él."""

    lot = models.OneToOneField(
        "lots.Lot",
        on_delete=models.PROTECT,
        primary_key=True,
        related_name="drying",
    )
    # Queda guardada después de liberar la marquesina: es el historial de uso de la marquesina.
    facility = models.ForeignKey(
        "facilities.PostharvestFacility",
        on_delete=models.PROTECT,
        related_name="drying_processes",
    )
    started_at = models.DateTimeField()
    entry_moisture_pct = _percent()
    # Se inició con una humedad fuera del rango esperado del productor, con la confirmación de
    # quien lo registró.
    entry_moisture_out_of_range = models.BooleanField(default=False)
    # PROTECT: una cuenta que respondió por un secado no se elimina.
    responsible = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # El resultado: todo o nada, se guarda al finalizar.
    ended_at = models.DateTimeField(null=True, blank=True)
    final_moisture_pct = _percent(null=True, blank=True)
    dry_weight_kg = models.DecimalField(
        max_digits=7, decimal_places=ONE_DECIMAL, null=True, blank=True
    )
    yield_pct = _percent(null=True, blank=True)
    # Se guarda al finalizar, cuando la bitácora ya no cambia.
    total_sun_hours = models.DecimalField(
        max_digits=5, decimal_places=ONE_DECIMAL, null=True, blank=True
    )
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
                condition=_between("entry_moisture_pct", 0, MAX_PERCENT),
                name="drying_process_entry_moisture_range",
            ),
            models.CheckConstraint(
                condition=models.Q(**{f"{name}__isnull": True for name in RESULT_FIELDS})
                | models.Q(**{f"{name}__isnull": False for name in RESULT_FIELDS}),
                name="drying_process_result_all_or_none",
            ),
            models.CheckConstraint(
                condition=models.Q(ended_at__isnull=True)
                | models.Q(ended_at__gt=models.F("started_at")),
                name="drying_process_ends_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(dry_weight_kg__isnull=True) | models.Q(dry_weight_kg__gt=0),
                name="drying_process_dry_weight_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(yield_pct__isnull=True) | _between("yield_pct", 0, MAX_PERCENT),
                name="drying_process_yield_range",
            ),
            models.CheckConstraint(
                condition=models.Q(final_moisture_pct__isnull=True)
                | _between("final_moisture_pct", 0, MAX_PERCENT),
                name="drying_process_final_moisture_range",
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados.
        default_permissions = ()
        permissions = [
            ("log_drying", "Puede registrar, corregir y eliminar la bitácora de secado"),
            ("manage_drying", "Puede iniciar y finalizar secados"),
        ]

    def __str__(self):
        return str(self.lot)


class DryingLogEntry(models.Model):
    """La bitácora de un día de secado: la humedad medida a una hora, las horas al sol y a la
    sombra, los volteos y el clima. Una por fecha."""

    # Lo genera el dispositivo, para que un reenvío desde la cola no cree otra bitácora.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Un secado no se elimina: el CASCADE solo ordena el modelo.
    process = models.ForeignKey(
        DryingProcess,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    measured_at = models.DateTimeField()
    # La fecha local de la medición y su número de día contando desde la fecha de inicio. Los
    # calcula el servicio; se guardan para la regla de una bitácora por fecha y para las alertas.
    log_date = models.DateField()
    day_number = models.PositiveSmallIntegerField()
    moisture_pct = _percent()
    sun_hours = _day_hours()
    shade_hours = _day_hours(null=True, blank=True)
    turn_count = models.PositiveSmallIntegerField()
    # Cada cuántas horas se volteó; no hay frecuencia sin volteos.
    turn_frequency_hours = _day_hours(null=True, blank=True)
    weather = models.CharField(max_length=16, choices=Weather.choices)
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
        ordering = ["measured_at"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(
                fields=["process", "log_date"], name=LOG_DATE_UNIQUE_CONSTRAINT
            ),
            models.CheckConstraint(
                condition=models.Q(day_number__gte=1), name="drying_log_day_positive"
            ),
            models.CheckConstraint(
                condition=_between("moisture_pct", 0, MAX_PERCENT),
                name="drying_log_moisture_range",
            ),
            models.CheckConstraint(
                condition=_between("sun_hours", 0, MAX_DAY_HOURS),
                name="drying_log_sun_hours_range",
            ),
            models.CheckConstraint(
                condition=models.Q(shade_hours__isnull=True)
                | _between("shade_hours", 0, MAX_DAY_HOURS),
                name="drying_log_shade_hours_range",
            ),
            models.CheckConstraint(
                condition=models.Q(turn_count__lte=MAX_TURNS_PER_DAY),
                name="drying_log_turn_count_range",
            ),
            models.CheckConstraint(
                condition=models.Q(turn_count=0, turn_frequency_hours__isnull=True)
                # Sin el `isnull`, una frecuencia vacía con volteos pasaría: en SQL una comparación
                # con NULL no es falsa, y un CHECK que no es falso se cumple.
                | (
                    models.Q(turn_count__gt=0, turn_frequency_hours__isnull=False)
                    & _between("turn_frequency_hours", MIN_TURN_FREQUENCY_HOURS, MAX_DAY_HOURS)
                ),
                name="drying_log_turn_frequency_with_turns",
            ),
            models.CheckConstraint(
                condition=models.Q(weather__in=Weather.values), name="drying_log_weather_choice"
            ),
        ]
        indexes = [
            models.Index(fields=["process", "measured_at"], name="drying_log_process_time_idx"),
        ]

    def __str__(self):
        return f"{self.process} · día {self.day_number}"


class DryingProcessAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        STARTED = "started", "Secado iniciado"
        UPDATED = "updated", "Inicio corregido"
        FINISHED = "finished", "Secado finalizado"
        LOG_CREATED = "log_created", "Bitácora registrada"
        LOG_UPDATED = "log_updated", "Bitácora corregida"
        LOG_DELETED = "log_deleted", "Bitácora eliminada"

    # Un secado no se elimina, así que su historial apunta a él directamente.
    process = models.ForeignKey(
        DryingProcess,
        on_delete=models.PROTECT,
        related_name="audit_events",
    )
    # La bitácora de los eventos `log_*`, por su id: una bitácora eliminada deja su copia aquí.
    log_ref = models.UUIDField(null=True, blank=True, db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="drying_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión del secado o de la bitácora que dejó este cambio.
    version = models.PositiveIntegerField()
    # Por cada campo cambiado, su valor anterior y nuevo con los textos de la API. Un secado no
    # tiene datos personales: las cuentas se guardan por su id.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
