import uuid

from django.db import models
from django.db.models import Q

from apps.common.audit import AuditEventBase


class Harvest(models.Model):
    """Una recolección de cacao en una sola parcela y en una fecha, con su peso en verde y su
    variedad. Se corrige mientras no forme un lote."""

    # Lo genera el dispositivo: la cosecha se captura sin conexión y la cola debe poder reenviar
    # sin duplicar.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # No cambia de parcela: si se eligió mal, se elimina y se registra de nuevo.
    plot = models.ForeignKey(
        "plots.Plot",
        on_delete=models.PROTECT,
        related_name="harvests",
    )
    harvest_date = models.DateField()
    # Peso del cacao en baba, el grano fresco recién sacado de la mazorca, en kilogramos. Es la
    # base del rendimiento del secado.
    green_weight_kg = models.DecimalField(max_digits=7, decimal_places=1)
    # Una variedad cosechada no se borra del catálogo.
    variety = models.ForeignKey(
        "crops.CacaoVariety",
        on_delete=models.PROTECT,
        related_name="harvests",
    )
    # Quien responde por la recolección, no cada jornalero. Una cuenta recolectora no se elimina:
    # se desactiva y la cosecha la conserva.
    collector = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="+",
    )
    # La versión de la ficha de la parcela al registrar la cosecha o al cambiar su variedad: si la
    # ficha cambia después, el historial de la ficha muestra lo que decía al cosechar.
    characterization_version = models.PositiveIntegerField()
    # Quién la registró, que puede no ser el recolector. Si su cuenta se elimina, el registro se
    # conserva.
    registered_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )
    # Hora del dispositivo al capturar, solo informativa: el orden y los conflictos se deciden con
    # `version` y con la hora del servidor.
    captured_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.harvest_date} · {self.plot} · {self.green_weight_kg} kg"

    class Meta:
        ordering = ["-harvest_date", "-created_at", "id"]
        indexes = [
            models.Index(fields=["plot", "harvest_date"], name="harvests_plot_date_idx"),
            models.Index(fields=["harvest_date"], name="harvests_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(green_weight_kg__gt=0), name="harvests_green_weight_positive"
            ),
        ]
        # Se declaran a mano, en español, para que el productor los lea al armar un rol para sus
        # empleados. Eliminar es solo para lo registrado por error.
        default_permissions = ()
        permissions = [
            ("view_harvest", "Puede consultar cosechas"),
            ("add_harvest", "Puede registrar cosechas"),
            ("change_harvest", "Puede corregir cosechas que aún no forman un lote"),
            ("delete_harvest", "Puede eliminar cosechas registradas por error"),
        ]


class HarvestAuditEvent(AuditEventBase):
    class Action(models.TextChoices):
        CREATED = "created", "Cosecha registrada"
        UPDATED = "updated", "Cosecha corregida"
        DELETED = "deleted", "Cosecha eliminada"

    # El historial sobrevive a la cosecha y a quien actuó: al eliminar una cosecha registrada por
    # error, sus eventos quedan sin la relación pero con la copia de `harvest_ref` y `plot_ref`.
    harvest = models.ForeignKey(
        Harvest,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_events",
    )
    harvest_ref = models.UUIDField(db_index=True)
    plot_ref = models.UUIDField()
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="harvest_audit_events",
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    version = models.PositiveIntegerField()
    # El valor anterior y el nuevo de cada campo que cambió. La variedad y el recolector van por
    # su id, nunca por su nombre, para que el historial no copie datos personales.
    changes = models.JSONField(default=dict)

    class Meta(AuditEventBase.Meta):
        default_permissions = ()
