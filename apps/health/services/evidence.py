"""Las fotos de evidencia de un monitoreo o de un control realizados."""

from django.db import transaction

from apps.common.files import JPEG, PNG, clean_file_name, detect_format
from apps.common.locks import lock_aggregate_root
from apps.common.ownership import owner_filter
from apps.common.roles import is_employee

from ..exceptions import (
    EvidenceDeleteNotAllowed,
    EvidenceFormatNotAllowed,
    EvidenceIdConflict,
    EvidenceLimitReached,
    EvidenceNotAllowed,
    EvidenceNotFound,
    EvidenceRequiresDone,
    EvidenceTargetNotFound,
    EvidenceTooLarge,
)
from ..models import (
    HealthEvidenceAuditEvent,
    PhytosanitaryMonitoring,
    PhytosanitaryMonitoringEvidence,
    PhytosanitaryTreatment,
    PhytosanitaryTreatmentEvidence,
)
from .shared import ACTIVITY_DONE, SCHEDULE_PERMISSION, AgriculturalActivity, activity_scope

MAX_BYTES = 5 * 1024 * 1024
MAX_PER_RECORD = 5
NAME_MAX = 100
MONITORING = "phytosanitary_monitoring"
CONTROL = "phytosanitary_control"
# Solo fotos: el teléfono las toma o las elige de la galería.
FORMATS = (JPEG, PNG)
# Cómo se llega desde cada tabla de evidencia a la finca, para el alcance.
EVIDENCE_TABLES = (
    (PhytosanitaryMonitoringEvidence, "monitoring__activity__plot__farm"),
    (PhytosanitaryTreatmentEvidence, "treatment__activity__plot__farm"),
)


@transaction.atomic
def attach_evidence(actor, activity_id, data: dict):
    """Adjunta una foto a un monitoreo o a un control realizados. Devuelve `(foto, creada)`: la
    misma foto reenviada por la cola responde sin duplicarla.

    El archivo ya llegó completo antes de esta función, así que el bloqueo no dura lo que tarda
    la subida por la red. Sí incluye la escritura de la foto (hasta 5 MB) en la base de datos:
    se acepta porque el teléfono la reduce a unos cientos de KB y la finca atiende una escritura
    a la vez durante milisegundos. Si algo falla, la foto no queda guardada.
    """
    uploaded = data["file"]
    if uploaded.size > MAX_BYTES:
        raise EvidenceTooLarge()
    file_format = detect_format(uploaded, FORMATS)
    if file_format is None:
        raise EvidenceFormatNotAllowed()

    activity = _locked_activity(actor, activity_id)
    parent, model, parent_field = _parent(activity)
    activity.ensure_completable_by(actor)

    existing = find_evidence(data["id"])
    if existing is not None:
        if type(existing) is model and getattr(existing, f"{parent_field}_id") == parent.pk:
            return existing, False
        raise EvidenceIdConflict()
    if model.objects.filter(**{parent_field: parent}).count() >= MAX_PER_RECORD:
        raise EvidenceLimitReached()

    evidence = model(
        id=data["id"],
        file_name=clean_file_name(uploaded.name, max_length=NAME_MAX, fallback="foto"),
        content_type=file_format.content_type,
        size=uploaded.size,
        uploaded_by=actor,
        captured_at=data.get("captured_at"),
        **{parent_field: parent},
    )
    # El nombre en el almacenamiento es del servidor: nunca el que mandó el cliente.
    evidence.file.save(f"evidence/{evidence.pk}.{file_format.extension}", uploaded, save=False)
    evidence.save(force_insert=True)
    HealthEvidenceAuditEvent.objects.create(
        evidence_ref=evidence.pk,
        activity_ref=activity.pk,
        actor=actor,
        action=HealthEvidenceAuditEvent.Action.UPLOADED,
    )
    return evidence, True


def list_evidence(actor, activity_id) -> list:
    """Las fotos de un monitoreo o un control, de la primera a la última. Uno que todavía no se
    realizó no tiene."""
    activity = AgriculturalActivity.objects.filter(pk=activity_id, **activity_scope(actor)).first()
    if activity is None:
        raise EvidenceTargetNotFound()
    _ensure_allowed_type(activity)
    if activity.status != ACTIVITY_DONE:
        return []
    parent, model, parent_field = _parent(activity)
    return list(
        model.objects.filter(**{parent_field: parent})
        .select_related("uploaded_by")
        .order_by("uploaded_at", "id")
    )


def find_evidence(evidence_id, actor=None):
    """La foto, en cualquiera de las dos tablas. Con `actor`, solo si alcanza su finca."""
    for model, farm in EVIDENCE_TABLES:
        scope = {}
        if actor is not None:
            scope = owner_filter(actor, f"{farm}__producer_id", farm=f"{farm}_id")
        evidence = model.objects.filter(pk=evidence_id, **scope).first()
        if evidence is not None:
            return evidence
    return None


def visible_evidence(actor, evidence_id):
    evidence = find_evidence(evidence_id, actor)
    if evidence is None:
        raise EvidenceNotFound()
    return evidence


@transaction.atomic
def delete_evidence(actor, evidence_id) -> None:
    """Elimina una foto equivocada. La elimina quien la subió, quien programa labores en la finca
    (el Capataz/Operario o un rol propio con ese permiso, se llame como se llame) o el Productor y
    la cuenta técnica. El archivo se borra del almacenamiento después de confirmar la
    transacción: si algo falla antes, la foto sigue completa."""
    evidence = _locked_evidence(actor, evidence_id)
    uploaded_it = evidence.uploaded_by_id is not None and evidence.uploaded_by_id == actor.pk
    if not (uploaded_it or not is_employee(actor) or actor.has_perm(SCHEDULE_PERMISSION)):
        raise EvidenceDeleteNotAllowed()

    # El monitoreo y el control llevan el `id` de su actividad.
    activity_ref = getattr(evidence, "monitoring_id", None) or evidence.treatment_id
    storage, name = evidence.file.storage, evidence.file.name
    evidence_ref = evidence.pk
    evidence.delete()
    HealthEvidenceAuditEvent.objects.create(
        evidence_ref=evidence_ref,
        activity_ref=activity_ref,
        actor=actor,
        action=HealthEvidenceAuditEvent.Action.DELETED,
    )
    transaction.on_commit(lambda: storage.delete(name))


def _locked_evidence(actor, evidence_id):
    """La foto, con la finca de su registro bloqueada hasta el final de la transacción."""
    for model, farm in EVIDENCE_TABLES:
        if model.objects.filter(pk=evidence_id).exists():
            evidence, _ = lock_aggregate_root(
                model,
                evidence_id,
                root=farm,
                scope=owner_filter(actor, f"{farm}__producer_id", farm=f"{farm}_id"),
                not_found=EvidenceNotFound,
            )
            return evidence
    raise EvidenceNotFound()


def _locked_activity(actor, activity_id):
    activity, _ = lock_aggregate_root(
        AgriculturalActivity,
        activity_id,
        root="plot__farm",
        scope=activity_scope(actor),
        not_found=EvidenceTargetNotFound,
    )
    _ensure_allowed_type(activity)
    if activity.status != ACTIVITY_DONE:
        # La foto respalda lo que ya se observó o se aplicó.
        raise EvidenceRequiresDone()
    return activity


def _ensure_allowed_type(activity) -> None:
    if activity.activity_type not in (MONITORING, CONTROL):
        raise EvidenceNotAllowed()


def _parent(activity):
    """El registro de sanidad del que cuelga la foto, su tabla de evidencia y el campo que los
    une."""
    if activity.activity_type == MONITORING:
        parent = PhytosanitaryMonitoring.objects.filter(activity=activity).first()
        model, field = PhytosanitaryMonitoringEvidence, "monitoring"
    else:
        parent = PhytosanitaryTreatment.objects.filter(activity=activity).first()
        model, field = PhytosanitaryTreatmentEvidence, "treatment"
    if parent is None:
        # Una actividad realizada de estos tipos siempre tiene su registro de sanidad; sin él no
        # hay nada que respaldar.
        raise EvidenceNotAllowed()
    return parent, model, field
