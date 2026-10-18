from collections.abc import Callable

from django.db.models import QuerySet

from apps.common.ownership import owner_filter

from ..exceptions import FarmNotFound, PlotNotFound
from .shared import AgriculturalActivity, activity_scope

# Los modelos de la parcela y de la finca se toman de las relaciones y no de sus apps: ninguna app
# importa de otra.
Plot = AgriculturalActivity._meta.get_field("plot").related_model
Farm = Plot._meta.get_field("farm").related_model


def monitoring_history(actor, filters: dict) -> tuple[QuerySet, Callable]:
    """Los monitoreos realizados de todo lo que `actor` alcanza, del más reciente al más antiguo, y
    la función que dice qué detecciones mostrar de cada uno. `farm` y `plot` los acotan (una finca
    o una parcela que no alcanza es 404, como lo de otro productor). Con un filtro de plaga (o de
    Otra) solo vienen los monitoreos donde se detectó, y de cada uno solo esa detección."""
    if filters.get("plot") is not None and not _reaches(Plot, filters["plot"], actor, "farm"):
        raise PlotNotFound()
    if filters.get("farm") is not None and not _reaches(Farm, filters["farm"], actor, ""):
        raise FarmNotFound()

    activities = AgriculturalActivity.objects.filter(
        phytosanitary_monitoring__isnull=False, **activity_scope(actor)
    )
    if actor.is_superuser and filters.get("producer") is not None:
        activities = activities.filter(plot__farm__producer_id=filters["producer"])
    if filters.get("plot") is not None:
        activities = activities.filter(plot_id=filters["plot"])
    if filters.get("farm") is not None:
        activities = activities.filter(plot__farm_id=filters["farm"])
    if filters.get("from") is not None:
        activities = activities.filter(done_date__gte=filters["from"])
    if filters.get("to") is not None:
        activities = activities.filter(done_date__lte=filters["to"])

    pest_id = filters.get("pest_disease")
    if pest_id is not None:
        activities = activities.filter(
            phytosanitary_monitoring__detections__pest_disease_id=pest_id
        )

        def keep(detection):
            return detection.pest_disease_id == pest_id

    elif filters.get("other"):
        activities = activities.filter(
            phytosanitary_monitoring__detections__other_description__isnull=False
        ).distinct()

        def keep(detection):
            return detection.pest_disease_id is None

    else:

        def keep(detection):
            return True

    ordered = activities.order_by("-done_date", "-id")
    return AgriculturalActivity.with_representation(ordered), keep


def _reaches(model, pk, actor, farm_path: str) -> bool:
    """Si `actor` alcanza la finca (`farm_path` vacío) o la parcela (`"farm"`) con ese id."""
    prefix = f"{farm_path}__" if farm_path else ""
    farm = f"{farm_path}_id" if farm_path else "id"
    scope = owner_filter(actor, f"{prefix}producer_id", farm=farm)
    return model.objects.filter(pk=pk, **scope).exists()


def pest_summary(activities: list, keep: Callable) -> list[dict]:
    """Por cada plaga (y cada texto de Otra), la última incidencia y la anterior, para ver si sube
    o baja. Solo compara monitoreos del mismo tipo de muestreo: un 24 % de mazorcas no es menos que
    un 31 % de árboles. `activities` va del más reciente al más antiguo."""
    seen: dict[tuple, list] = {}
    for activity in activities:
        monitoring = activity.phytosanitary_monitoring
        for detection in monitoring.detections.all():
            if not keep(detection):
                continue
            key = (
                ("pest", detection.pest_disease_id)
                if detection.pest_disease_id is not None
                else ("other", detection.normalized_other)
            )
            seen.setdefault(key, []).append((activity, monitoring, detection))

    rows = []
    for occurrences in seen.values():
        latest_activity, latest_monitoring, latest = occurrences[0]
        previous = next(
            (
                detection
                for _, monitoring, detection in occurrences[1:]
                if monitoring.sampling_unit == latest_monitoring.sampling_unit
            ),
            None,
        )
        rows.append(
            {
                "pest_disease": latest.pest_disease,
                "other_description": latest.other_description,
                "sampling_unit": latest_monitoring.sampling_unit,
                "latest_incidence": latest.incidence,
                "previous_incidence": previous.incidence if previous is not None else None,
                "latest_date": latest_activity.done_date,
            }
        )
    # Lo que más afecta, primero.
    return sorted(
        rows,
        key=lambda row: (
            -row["latest_incidence"],
            row["pest_disease"].name if row["pest_disease"] else row["other_description"],
        ),
    )
