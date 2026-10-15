import uuid

from django.db import models

from .results import PhytosanitaryMonitoring, PhytosanitaryTreatment


class EvidenceBase(models.Model):
    """Lo común a una foto de evidencia, con una tabla por registro que la tiene: así cada foto
    pertenece a exactamente un registro por construcción, sin una clave foránea por cada padre
    posible.

    El archivo va al almacenamiento por defecto de Django; este modelo no sabe dónde queda.
    """

    # Lo genera el dispositivo: la foto espera en la cola sin conexión y un reenvío no la duplica.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # El nombre en el almacenamiento lo pone el servidor (`evidence/{id}.jpg`), nunca el cliente.
    file = models.FileField(max_length=150)
    # El nombre que tenía en el teléfono, sin la carpeta, para mostrarlo.
    file_name = models.CharField(max_length=100)
    # El que dicen los primeros bytes del archivo, no el que envió el cliente.
    content_type = models.CharField(max_length=20)
    size = models.PositiveIntegerField()
    # Quien la subió; si su cuenta se elimina, la foto se conserva.
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    # Hora del dispositivo al tomarla, solo informativa.
    captured_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["uploaded_at", "id"]
        default_permissions = ()


class PhytosanitaryMonitoringEvidence(EvidenceBase):
    monitoring = models.ForeignKey(
        PhytosanitaryMonitoring, on_delete=models.CASCADE, related_name="evidence"
    )

    class Meta(EvidenceBase.Meta):
        pass


class PhytosanitaryTreatmentEvidence(EvidenceBase):
    treatment = models.ForeignKey(
        PhytosanitaryTreatment, on_delete=models.CASCADE, related_name="evidence"
    )

    class Meta(EvidenceBase.Meta):
        pass


class HealthEvidenceAuditEvent(models.Model):
    """Quién adjuntó o eliminó cada foto. Sobrevive a la foto y al registro: guarda sus ids, sin
    el archivo ni nombres de personas."""

    class Action(models.TextChoices):
        UPLOADED = "uploaded", "Evidencia adjuntada"
        DELETED = "deleted", "Evidencia eliminada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    evidence_ref = models.UUIDField(db_index=True)
    # La actividad (monitoreo o control) a la que pertenecía la foto.
    activity_ref = models.UUIDField()
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        default_permissions = ()
