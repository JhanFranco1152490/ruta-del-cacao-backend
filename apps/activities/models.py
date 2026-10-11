import uuid

from django.db import models
from django.db.models import Q

from apps.common.audit import AuditEventBase

from .choices import ActivityStatus, ActivityType


class AgriculturalActivity(models.Model):
    """Una labor sobre una parcela: se programa, se puede reprogramar mientras no se haga y, al
    hacerse, se registra su realización, que ya no cambia."""

    # Lo genera el dispositivo: la realización se captura sin conexión y la cola debe poder
    # reenviar sin duplicar.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # No cambia de parcela: lo hecho en ella quedaría atribuido a otra.
    plot = models.ForeignKey(
        "plots.Plot",
        on_delete=models.PROTECT,
        related_name="agricultural_activities",
    )
    activity_type = models.CharField(max_length=32, choices=ActivityType.choices)
    other_description = models.CharField(max_length=80, null=True, blank=True)
    scheduled_date = models.DateField()
    # Una cuenta responsable de alguna labor no se elimina: se desactiva y la labor la conserva.
    assignee = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
    )
    status = models.CharField(
        max_length=16, choices=ActivityStatus.choices, default=ActivityStatus.SCHEDULED
    )
    # La fecha en que se hizo la labor, que puede no ser la programada ni la del registro.
    done_date = models.DateField(null=True, blank=True)
    # Quién la registró, que puede no ser el responsable. Si su cuenta se elimina, el registro
    # se conserva.
    completed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Cuándo llegó la realización al servidor.
    completed_at = models.DateTimeField(null=True, blank=True)
    # Hora del dispositivo al capturar la realización, solo informativa.
    captured_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scheduled_date", "activity_type", "id"]
        indexes = [
            models.Index(fields=["plot", "scheduled_date"], name="activities_plot_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(activity_type=ActivityType.OTHER, other_description__isnull=False)
                    & ~Q(other_description="")
                )
                | (~Q(activity_type=ActivityType.OTHER) & Q(other_description__isnull=True)),
                name="activities_other_description_only_with_other",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        status=ActivityStatus.DONE,
                        done_date__isnull=False,
                        completed_at__isnull=False,
                    )
                )
                | Q(
                    status=ActivityStatus.SCHEDULED,
                    done_date__isnull=True,
                    completed_at__isnull=True,
                ),
                name="activities_completion_data_only_when_done",
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados. Registrar la realización va aparte de editar: un productor puede querer que
        # alguien cierre sus labores sin poder cambiar la planeación.
        default_permissions = ()
        permissions = [
            ("view_agriculturalactivity", "Puede consultar actividades agrícolas"),
            ("add_agriculturalactivity", "Puede programar actividades agrícolas"),
            ("change_agriculturalactivity", "Puede editar y reprogramar actividades agrícolas"),
            (
                "complete_agriculturalactivity",
                "Puede registrar la realización de actividades agrícolas",
            ),
            (
                "delete_agriculturalactivity",
                "Puede eliminar actividades agrícolas programadas por error",
            ),
        ]


class AgriculturalActivityInput(models.Model):
    """Un insumo que se gastó en una labor, con su cantidad en la unidad del insumo. Se registra
    con la realización y no cambia después."""

    activity = models.ForeignKey(
        AgriculturalActivity, on_delete=models.CASCADE, related_name="inputs"
    )
    # Un insumo usado no se elimina aunque dos operaciones se crucen: la base es la garantía final.
    input = models.ForeignKey(
        "inputs.AgriculturalInput", on_delete=models.PROTECT, related_name="activity_uses"
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    # La salida que esta labor dejó en el inventario de la finca. La relación va de aquí hacia los
    # insumos, para que esa app no tenga que conocer las actividades.
    stock_movement = models.OneToOneField(
        "inputs.InputMovement", on_delete=models.PROTECT, related_name="activity_use"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "input"], name="activities_input_once_per_activity"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="activities_input_quantity_positive"
            ),
        ]
        default_permissions = ()


class AgriculturalActivityAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Actividad programada"
        UPDATED = "updated", "Actividad actualizada"
        COMPLETED = "completed", "Realización registrada"
        DELETED = "deleted", "Actividad eliminada"

    # El historial sobrevive a la actividad y a quien actuó: al eliminar una programada por
    # error, sus eventos quedan sin la relación pero con la copia de `activity_ref` y
    # `plot_ref`.
    activity = models.ForeignKey(
        AgriculturalActivity,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    activity_ref = models.UUIDField(db_index=True)
    plot_ref = models.UUIDField()
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="agricultural_activity_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    version = models.PositiveIntegerField()
    # El valor anterior y el nuevo de cada campo que cambió. Una persona va por su id, nunca por
    # su nombre, para que el historial no copie datos personales.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
