from collections.abc import Callable

from apps.common.ownership import owner_filter

from ..exceptions import PlotNotFound
from ..models import PhytosanitaryMonitoring

# Los modelos de la actividad y de la parcela se toman de las relaciones y no de sus apps: ninguna
# app importa de otra.
AgriculturalActivity = PhytosanitaryMonitoring._meta.get_field("activity").related_model
Plot = AgriculturalActivity._meta.get_field("plot").related_model


def plot_history(actor, plot_id, filters: dict) -> tuple[list, Callable]:
    """Los monitoreos realizados de una parcela, del más reciente al más antiguo, y la función que
    dice qué detecciones mostrar de cada uno. Con un filtro de plaga (o de Otra) solo vienen los
    monitoreos donde se detectó, y de cada uno solo esa detección."""
    plot = Plot.objects.filter(
        pk=plot_id, **owner_filter(actor, "farm__producer_id", farm="farm_id")
    ).first()
    if plot is None:
        raise PlotNotFound()

    activities = AgriculturalActivity.objects.filter(
        plot=plot, phytosanitary_monitoring__isnull=False
    )
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
    return list(AgriculturalActivity.with_representation(ordered)), keep


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
