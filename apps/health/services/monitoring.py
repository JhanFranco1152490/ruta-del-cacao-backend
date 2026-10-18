from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.common.locks import lock_aggregate_root
from apps.common.plot_trees import tree_count
from apps.common.text import normalize_catalog_name

from ..choices import SamplingUnit
from ..exceptions import (
    InvalidResult,
    MonitoringAlreadyRecorded,
    MonitoringNotFound,
    NotAMonitoring,
    PestDiseaseInactive,
)
from ..models import Detection, PestDisease, PhytosanitaryMonitoring, PhytosanitaryTreatment
from .controls import add_control, clean_control, treatment_values
from .shared import ACTIVITY_DONE, AgriculturalActivity, activity_scope

MONITORING_TYPE = "phytosanitary_monitoring"
PERCENT_PLACES = Decimal("0.01")
REPEATED = "Esta plaga o enfermedad ya está en la lista. Modifica la detección existente."


@transaction.atomic
def record_monitoring(actor, activity_id, data: dict):
    """Registra el resultado de un monitoreo y lo marca realizado. Devuelve `(actividad, creado)`.

    Llega desde la cola del dispositivo: el mismo resultado reenviado (también con las detecciones
    en otro orden) responde sin escribir nada; otro resultado sobre uno ya registrado es un
    conflicto, porque un monitoreo registrado no se corrige.

    Cada detección puede traer su control: hecho en el momento (con la fecha del monitoreo, a
    nombre de quien registra) o programado para después. Todo va en la misma transacción: si un
    control no es válido, no se guarda el monitoreo.
    """
    activity, _ = lock_aggregate_root(
        AgriculturalActivity,
        activity_id,
        root="plot__farm",
        scope=activity_scope(actor),
        not_found=MonitoringNotFound,
    )
    if activity.activity_type != MONITORING_TYPE:
        raise NotAMonitoring()
    activity.ensure_completable_by(actor)

    detections = _clean_detections(data)
    if activity.status == ACTIVITY_DONE:
        if _same_result(activity, data, detections):
            return activity, False
        raise MonitoringAlreadyRecorded()

    _ensure_within_the_plot(activity, data)
    pests = _active_pests(detections)
    _ensure_new_ids(detections)
    requested_at = timezone.now()
    monitoring = PhytosanitaryMonitoring.objects.create(
        activity=activity,
        sampling_unit=data["sampling_unit"],
        evaluated_units=data["evaluated_units"],
        sampling_method=data["sampling_method"],
        notes=_clean_text(data["notes"]),
        no_presence=data["no_presence"],
    )
    created = Detection.objects.bulk_create(
        [
            Detection(
                id=row["id"],
                monitoring=monitoring,
                pest_disease=pests.get(row["pest_disease_id"]),
                other_description=row["other_description"],
                normalized_other=row["normalized_other"],
                affected_units=row["affected_units"],
                incidence=incidence(row["affected_units"], data["evaluated_units"]),
                control_requested_by=actor if row["control_requested"] else None,
                control_requested_at=requested_at if row["control_requested"] else None,
            )
            for row in detections
        ]
    )
    activity.complete_with_result(actor, data["done_date"], data["captured_at"])
    for row, detection in zip(detections, created, strict=True):
        if row["control"] is not None:
            add_control(
                actor,
                detection,
                activity,
                _with_monitoring_data(row["control"], actor, activity, data),
            )
    return activity, True


def _with_monitoring_data(control: dict, actor, activity, data: dict) -> dict:
    """Un control hecho en el momento toma la fecha del monitoreo y queda a nombre de quien lo
    registra. La cuenta técnica nunca es responsable de una labor: con ella queda el responsable
    del monitoreo."""
    if control["mode"] != "done":
        return control
    assignee_id = activity.assignee_id if actor.is_superuser else actor.pk
    return {
        **control,
        "done_date": data["done_date"],
        "assignee_id": assignee_id,
        "captured_at": data["captured_at"],
    }


def incidence(affected: int, evaluated: int) -> Decimal:
    """Unidades afectadas ÷ evaluadas × 100, con dos decimales y la mitad hacia arriba, como se
    redondea a mano: 0,125 % es 0,13 % y no 0,12 %."""
    return (Decimal(affected) * 100 / Decimal(evaluated)).quantize(
        PERCENT_PLACES, rounding=ROUND_HALF_UP
    )


def _ensure_within_the_plot(activity, data: dict) -> None:
    """No se evalúan más árboles de los que tiene la parcela según su ficha. Las mazorcas no
    tienen un tope que la ficha conozca, y una parcela sin siembras registradas no limita nada:
    el monitoreo no debe esperar a la caracterización. Un resultado que ya se guardó no vuelve a
    revisarse (se llega aquí solo con uno nuevo), así que reenviarlo desde la cola sigue
    funcionando aunque la ficha cambie después."""
    if data["sampling_unit"] != SamplingUnit.TREES:
        return
    trees = tree_count(activity.plot_id)
    if trees is not None and data["evaluated_units"] > trees:
        raise InvalidResult(
            "evaluated_units",
            f"No puedes evaluar más árboles de los que tiene la parcela ({trees}).",
        )


def _clean_detections(data: dict) -> list[dict]:
    """Las detecciones validadas, con "Otra" recortada y normalizada."""
    evaluated = data["evaluated_units"]
    if evaluated <= 0:
        raise InvalidResult("evaluated_units", "Indica cuántas unidades evaluaste.")
    rows = data["detections"]
    if data["no_presence"] and rows:
        raise InvalidResult(
            "detections",
            "Un monitoreo sin presencia de plagas ni enfermedades no lleva detecciones.",
        )
    if not data["no_presence"] and not rows:
        raise InvalidResult("detections", "Agrega al menos una detección o marca Sin presencia.")

    cleaned, ids, pests, others = [], set(), set(), set()
    control_ids = set()
    for row in rows:
        other = _clean_text(row["other_description"])
        pest_id = row["pest_disease_id"]
        if (pest_id is None) == (other is None):
            raise InvalidResult(
                "detections", "Cada detección lleva una plaga o enfermedad del catálogo u Otra."
            )
        if row["affected_units"] <= 0:
            raise InvalidResult("detections", "Indica las unidades afectadas.")
        if row["affected_units"] > evaluated:
            raise InvalidResult(
                "detections",
                f"Las unidades afectadas no pueden superar las evaluadas ({evaluated}).",
            )
        if row["id"] in ids:
            raise InvalidResult("detections", "Dos detecciones tienen el mismo identificador.")
        normalized_other = normalize_catalog_name(other) if other is not None else None
        if pest_id is not None and pest_id in pests:
            raise InvalidResult("detections", REPEATED)
        if normalized_other is not None and normalized_other in others:
            raise InvalidResult("detections", REPEATED)
        control = clean_control(row["control"]) if row["control"] is not None else None
        if control is not None and row["control_requested"]:
            raise InvalidResult(
                "detections",
                "Una detección lleva su control o pide que se lo programen, no las dos.",
            )
        if control is not None:
            if control["id"] in control_ids:
                raise InvalidResult("detections", "Dos controles tienen el mismo identificador.")
            control_ids.add(control["id"])
        ids.add(row["id"])
        pests.add(pest_id)
        others.add(normalized_other)
        cleaned.append(
            {
                "id": row["id"],
                "pest_disease_id": pest_id,
                "other_description": other,
                "normalized_other": normalized_other,
                "affected_units": row["affected_units"],
                "control": control,
                "control_requested": row["control_requested"],
            }
        )
    return cleaned


def _active_pests(detections: list[dict]) -> dict:
    ids = {row["pest_disease_id"] for row in detections if row["pest_disease_id"] is not None}
    pests = {pest.pk: pest for pest in PestDisease.objects.filter(pk__in=ids)}
    if len(pests) != len(ids):
        # Un 400 y no un 404: la cola leería un 404 como un monitoreo eliminado y descartaría el
        # registro. Así llega a la bandeja y la persona elige otra.
        raise InvalidResult("detections", "La plaga o enfermedad no existe en el catálogo.")
    inactive = sorted((pk for pk, pest in pests.items() if not pest.is_active), key=str)
    if inactive:
        raise PestDiseaseInactive(inactive)
    return pests


def _ensure_new_ids(detections: list[dict]) -> None:
    # Un `id` que ya usa la detección de otro monitoreo. Las de este todavía no existen: un
    # reenvío del mismo resultado ya se respondió antes.
    if Detection.objects.filter(pk__in=[row["id"] for row in detections]).exists():
        raise InvalidResult("detections", "Ya existe una detección con este identificador.")


def _same_result(activity, data: dict, detections: list[dict]) -> bool:
    """Si lo enviado es el resultado ya registrado. Los controles se comparan por lo propio de
    cada uno (detección y qué se hizo), que no cambia: después del registro un control se puede
    reprogramar o realizar, y la detección puede ganar otros controles desde su detalle."""
    monitoring = PhytosanitaryMonitoring.objects.filter(activity=activity).first()
    if monitoring is None:
        return False
    stored = {
        "done_date": activity.done_date,
        "sampling_unit": monitoring.sampling_unit,
        "evaluated_units": monitoring.evaluated_units,
        "sampling_method": monitoring.sampling_method,
        "notes": monitoring.notes,
        "no_presence": monitoring.no_presence,
        "detections": {
            (
                row.pk,
                row.pest_disease_id,
                row.normalized_other,
                row.affected_units,
                row.control_requested_at is not None,
            )
            for row in monitoring.detections.all()
        },
    }
    sent = {
        "done_date": data["done_date"],
        "sampling_unit": data["sampling_unit"],
        "evaluated_units": data["evaluated_units"],
        "sampling_method": data["sampling_method"],
        "notes": _clean_text(data["notes"]),
        "no_presence": data["no_presence"],
        "detections": {
            (
                row["id"],
                row["pest_disease_id"],
                row["normalized_other"],
                row["affected_units"],
                row["control_requested"],
            )
            for row in detections
        },
    }
    if stored != sent:
        return False
    treatments = {
        treatment.pk: treatment_values(treatment)
        for treatment in PhytosanitaryTreatment.objects.filter(detection__monitoring=monitoring)
    }
    return all(
        treatments.get(row["control"]["id"])
        == (
            row["id"],
            row["control"]["method"],
            row["control"]["method_description"],
            row["control"]["planned_input_id"],
        )
        for row in detections
        if row["control"] is not None
    )


def _clean_text(text: str | None) -> str | None:
    return (text or "").strip() or None
