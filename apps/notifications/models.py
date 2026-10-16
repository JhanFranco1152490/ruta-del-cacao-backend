import uuid

from django.db import models
from django.db.models import Q

from .choices import ACTIVITY_KINDS, NotificationKind, NotificationSeverity


class Notification(models.Model):
    """El aviso que recibe una persona por una condición: una actividad próxima, retrasada o
    vencida. Si la condición le toca a tres personas, son tres avisos, y cada una lo lee o lo
    elimina por su cuenta."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=40, choices=NotificationKind.choices)
    severity = models.CharField(
        max_length=16, choices=NotificationSeverity.choices, default=NotificationSeverity.NORMAL
    )
    # Lo que hace única la condición dentro de su tipo (la actividad, su fecha y el día del
    # recordatorio): con ella, evaluar otra vez no repite el aviso.
    condition_key = models.CharField(max_length=120)
    # Los avisos "de lo mismo" (todos los de una actividad): el más nuevo de una persona oculta
    # los anteriores, y el teléfono reemplaza la push vieja por la nueva.
    thread_key = models.CharField(max_length=120)
    activity = models.ForeignKey(
        "activities.AgriculturalActivity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    # La fecha programada que tenía la actividad al avisar: si ya no es la misma, se reprogramó.
    condition_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    # Eliminada de la bandeja. La fila se queda: es lo que impide que la siguiente evaluación,
    # que vería la misma condición, vuelva a crear el aviso.
    dismissed_at = models.DateTimeField(null=True, blank=True)
    pushed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "kind", "condition_key"],
                name="notifications_once_per_condition",
            ),
            models.CheckConstraint(
                condition=~Q(kind__in=ACTIVITY_KINDS) | Q(activity__isnull=False),
                name="notifications_activity_kinds_have_activity",
            ),
        ]
        indexes = [
            models.Index(
                fields=["recipient", "dismissed_at", "read_at", "severity", "-created_at"],
                name="notifications_inbox_idx",
            ),
            models.Index(fields=["pushed_at", "created_at"], name="notifications_push_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.created_at:%Y-%m-%d}"


class PushSubscription(models.Model):
    """Un dispositivo en el que una persona activó las notificaciones push. Las llaves solo
    sirven para cifrar el aviso a ese navegador, no para entrar a la cuenta."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    # La dirección que el navegador da para ese dispositivo: identifica la suscripción.
    endpoint = models.TextField(unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    device_label = models.CharField(max_length=60, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return self.device_label or "Dispositivo"
