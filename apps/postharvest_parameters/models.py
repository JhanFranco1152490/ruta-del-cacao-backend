from django.db import models

from apps.common.audit import AuditEventBase

from .fields import (
    FIELDS,
    LIMITS,
    PERCENT_DECIMAL_PLACES,
    PERCENT_MAX_DIGITS,
    POSITIVE_FIELDS,
    RANGE_PAIRS,
)


def _percent():
    return models.DecimalField(
        max_digits=PERCENT_MAX_DIGITS, decimal_places=PERCENT_DECIMAL_PLACES
    )


def _constraints() -> list[models.CheckConstraint]:
    checks = []
    for name, kind in FIELDS.items():
        low, high = LIMITS[kind]
        checks.append(
            models.CheckConstraint(
                condition=models.Q(**{f"{name}__gte": low, f"{name}__lte": high}),
                name=f"postharvest_params_{name}_range",
            )
        )
    for low_name, high_name in RANGE_PAIRS:
        checks.append(
            models.CheckConstraint(
                condition=models.Q(**{f"{low_name}__lte": models.F(high_name)}),
                name=f"postharvest_params_{low_name}_not_above_max",
            )
        )
    for name in POSITIVE_FIELDS:
        checks.append(
            models.CheckConstraint(
                condition=models.Q(**{f"{name}__gt": 0}),
                name=f"postharvest_params_{name}_positive",
            )
        )
    return checks


class PostharvestParameters(models.Model):
    """Los parámetros de secado que un productor ajustó a su región. Valen para todas sus fincas.

    La fila solo existe si el productor guardó algo: sin ella se usa la línea base, y restablecer
    la borra. Se guardan los quince valores juntos, para que lo que el productor ve sea lo que se
    usa aunque la línea base cambie después.
    """

    producer = models.OneToOneField(
        "producers.Producer",
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="postharvest_parameters",
    )
    entry_moisture_min_pct = _percent()
    entry_moisture_max_pct = _percent()
    target_moisture_min_pct = _percent()
    target_moisture_max_pct = _percent()
    estimated_days_min = models.PositiveSmallIntegerField()
    estimated_days_max = models.PositiveSmallIntegerField()
    slow_stall_window_hours = models.PositiveSmallIntegerField()
    slow_stall_min_drop_pct = _percent()
    slow_duration_day = models.PositiveSmallIntegerField()
    slow_duration_moisture_pct = _percent()
    accelerated_day = models.PositiveSmallIntegerField()
    accelerated_moisture_pct = _percent()
    near_target_min_pct = _percent()
    near_target_max_pct = _percent()
    overdried_moisture_pct = _percent()
    updated_by = models.ForeignKey(
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
        verbose_name = "parámetros de poscosecha"
        verbose_name_plural = "parámetros de poscosecha"
        constraints = _constraints()
        default_permissions = ()
        permissions = [
            ("view_postharvestparameters", "Puede consultar los parámetros de poscosecha"),
            (
                "change_postharvestparameters",
                "Puede cambiar y restablecer los parámetros de poscosecha",
            ),
        ]

    def __str__(self):
        return f"Parámetros de {self.producer}"


class PostharvestParametersAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        UPDATED = "updated", "Parámetros actualizados"
        RESET = "reset", "Parámetros restablecidos a la línea base"

    # Apunta al productor y no a la fila, que restablecer borra. Se va con el productor creado por
    # error, como sus parámetros.
    producer = models.ForeignKey(
        "producers.Producer",
        on_delete=models.CASCADE,
        related_name="postharvest_parameters_audit_events",
    )
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="postharvest_parameters_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    # La versión que dejó este cambio; 0 al restablecer, porque ya no hay fila.
    version = models.PositiveIntegerField()
    # Por cada parámetro cambiado, su valor anterior y nuevo con los textos de la API. No hay datos
    # personales, así que se guardan los valores, como en los insumos.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
