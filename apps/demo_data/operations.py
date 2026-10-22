"""Lo que pasa en La Esperanza, la finca de demostración: sus empleados, insumos, infraestructura,
labores, monitoreos, cosechas y lotes, creados por los servicios de cada app con sus mismas reglas.

Cada parte revisa si ya está y solo agrega lo que falta, así que se puede repetir sin duplicar y
sin tocar lo que alguien haya hecho desde la aplicación. Lo que los servicios no dejan crear en el
pasado (programar una labor, registrar su realización) se crea hoy y se corre a su fecha.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

from apps.accounts.models import User
from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.users.creation import create_account
from apps.activities.choices import ActivityStatus, ActivityType
from apps.activities.models import AgriculturalActivity
from apps.activities.services.complete import complete_activity
from apps.activities.services.create import create_activity
from apps.activities.state import today_in_bogota
from apps.facilities.models import PostharvestFacility
from apps.facilities.services.create import create_facility
from apps.facilities.services.delete import delete_facility
from apps.farms.models import Farm
from apps.harvests.models import Harvest
from apps.harvests.services.create import create_harvest
from apps.health.models import PestDisease, PhytosanitaryMonitoring, PhytosanitaryTreatment
from apps.health.services.monitoring import record_monitoring
from apps.inputs.models import AgriculturalInput, InputMovement
from apps.inputs.services.create import create_input
from apps.inputs.services.movements import register_movement
from apps.lots.models import Lot
from apps.lots.services.create import create_lot
from apps.plots.models import Plot

from .catalog import (
    DEMO_EMPLOYEES,
    DEMO_FACILITIES,
    DEMO_FARM,
    DEMO_INPUTS,
    DEMO_PLOT,
    HISTORY_PLOT,
    LIVE_FACILITY_NAME,
)

MONITORING = ActivityType.PHYTOSANITARY_MONITORING


def seed_operations(owner: User, restore_account) -> list[str]:
    """Deja La Esperanza con vida y devuelve lo que hizo, una línea por parte. `owner` es la
    cuenta del productor; `restore_account` deja una cuenta activa y con la contraseña pública."""
    farm = Farm.objects.filter(producer=owner.producer, name=DEMO_FARM).first()
    if farm is None:
        return []
    notes = []
    employees = _employees(owner, restore_account)
    foreman = employees[DEMO_FARM]
    notes += _inputs(owner, farm)
    notes += _facilities(owner, farm)
    plot = Plot.objects.get(farm=farm, name=DEMO_PLOT)
    history_plot = Plot.objects.get(farm=farm, name=HISTORY_PLOT)
    notes += _scheduled_work(owner, foreman, plot, history_plot)
    notes += _monitoring_history(foreman, plot, history_plot)
    notes += _harvests_and_lots(owner, foreman, plot)
    return [note for note in notes if note]


def _employees(owner: User, restore_account) -> dict:
    """Los empleados de demostración por finca. Un empleado se crea una vez; la contraseña pública
    se le restablece siempre, como a las otras cuentas de demostración."""
    role = get_system_role(FOREMAN)
    by_farm = {}
    for definition in DEMO_EMPLOYEES:
        user = User.objects.filter(email__iexact=definition["email"]).first()
        if user is None:
            farm = Farm.objects.get(producer=owner.producer, name=definition["farm"])
            data = {key: value for key, value in definition.items() if key not in ("farm",)} | {
                "role_ids": [role.pk],
                "farm_ids": [farm.pk],
            }
            created = create_account(owner, data, uuid.uuid4())
            user = created.user
        restore_account(user, FOREMAN)
        by_farm[definition["farm"]] = user
    return by_farm


def _inputs(owner: User, farm: Farm) -> list[str]:
    created = 0
    for definition in DEMO_INPUTS:
        item = AgriculturalInput.objects.filter(
            producer=owner.producer, name=definition["name"]
        ).first()
        if item is not None:
            continue
        data = {key: value for key, value in definition.items() if key != "stock"}
        item = create_input(owner, {**data, "farm_id": farm.pk})
        register_movement(
            owner,
            {
                "kind": InputMovement.Kind.ENTRY,
                "farm_id": farm.pk,
                "input_id": item.pk,
                "quantity": definition["stock"],
                "occurred_on": today_in_bogota() - timedelta(days=30),
                "note": "Compra inicial",
            },
        )
        created += 1
    return [f"Insumos con existencias: {created}"] if created else []


def _facilities(owner: User, farm: Farm) -> list[str]:
    """Los cajones y la marquesina de la finca, y libre el nombre del cajón que se registra en
    vivo: si quedó de un ensayo y no tiene historial, se elimina; si lo tiene, se avisa."""
    notes = []
    created = 0
    for definition in DEMO_FACILITIES:
        if PostharvestFacility.objects.filter(farm=farm, name__iexact=definition["name"]).exists():
            continue
        create_facility(owner, {**definition, "farm_id": farm.pk})
        created += 1
    if created:
        notes.append(f"Cajones y marquesinas: {created}")
    left_over = PostharvestFacility.objects.filter(farm=farm, name__iexact=LIVE_FACILITY_NAME)
    for facility in left_over:
        try:
            delete_facility(owner, facility.pk, facility.version)
            notes.append(f"{LIVE_FACILITY_NAME} de un ensayo anterior: eliminado")
        except Exception:  # noqa: BLE001 - un elemento con historial no se elimina, solo se avisa
            notes.append(
                f"{LIVE_FACILITY_NAME} ya tiene historial: para repetir la demostración usa otro "
                "nombre"
            )
    return notes


def _schedule(owner: User, plot: Plot, activity_type, days_from_today: int, assignee: User):
    activity, _ = create_activity(
        owner,
        {
            "plot_id": plot.pk,
            "activity_type": activity_type,
            "scheduled_date": today_in_bogota() + timedelta(days=days_from_today),
            "assignee_id": assignee.pk,
            "other_description": None,
        },
    )
    return activity


def _move_to(activity: AgriculturalActivity, days_ago: int) -> None:
    """Pone una labor en su fecha del pasado. Los servicios no dejan programar ni realizar antes de
    hoy: se creó hoy y aquí se corre, igual que si se hubiera hecho ese día."""
    day = today_in_bogota() - timedelta(days=days_ago)
    changes = {"scheduled_date": day}
    if activity.status == ActivityStatus.DONE:
        changes["done_date"] = day
    AgriculturalActivity.objects.filter(pk=activity.pk).update(**changes)


def _scheduled_work(owner: User, foreman: User, plot: Plot, history_plot: Plot) -> list[str]:
    notes = []
    # Los monitoreos de hoy de la demostración: el primero se registra bien y el segundo, para el
    # caso con un dato incorrecto, no se guarda y sigue pendiente. Quedan programados cada vez que
    # no haya uno pendiente en su parcela.
    for target in (plot, history_plot):
        if not AgriculturalActivity.objects.filter(
            plot=target, activity_type=MONITORING, status=ActivityStatus.SCHEDULED
        ).exists():
            _schedule(owner, target, MONITORING, 0, foreman)
            notes.append(f"Monitoreo programado para hoy en {target.name}")
    if (
        AgriculturalActivity.objects.filter(plot__farm=plot.farm)
        .exclude(activity_type__in=[MONITORING, ActivityType.PHYTOSANITARY_CONTROL])
        .exists()
    ):
        return notes
    fertilization = _schedule(owner, plot, ActivityType.FERTILIZATION, 2, foreman)
    _schedule(owner, history_plot, ActivityType.PRUNING, 5, owner)
    _schedule(owner, plot, ActivityType.WEED_CONTROL, 9, foreman)
    # Una retrasada (uno y dos días) y una vencida (desde el tercero), para ver los dos estados.
    _move_to(_schedule(owner, plot, ActivityType.WEED_CONTROL, 0, foreman), 2)
    _move_to(_schedule(owner, history_plot, ActivityType.IRRIGATION, 0, foreman), 6)
    done = _schedule(owner, history_plot, ActivityType.WEED_CONTROL, 0, foreman)
    complete_activity(foreman, done.pk, {"done_date": today_in_bogota(), "inputs": []})
    _move_to(AgriculturalActivity.objects.get(pk=done.pk), 8)
    urea = AgriculturalInput.objects.get(producer=owner.producer, name=DEMO_INPUTS[0]["name"])
    applied = _schedule(owner, plot, ActivityType.FERTILIZATION, 0, foreman)
    complete_activity(
        foreman,
        applied.pk,
        {
            "done_date": today_in_bogota(),
            "inputs": [{"input_id": urea.pk, "quantity": Decimal("25")}],
        },
    )
    _move_to(AgriculturalActivity.objects.get(pk=applied.pk), 10)
    notes.append(
        f"Labores programadas, retrasada y realizadas ({fertilization.plot.code} y otras)"
    )
    return notes


def _pest(name: str) -> PestDisease:
    return PestDisease.objects.get(name=name)


def _detection(pest: PestDisease, affected: int, **extra) -> dict:
    return {
        "id": uuid.uuid4(),
        "pest_disease_id": pest.pk,
        "other_description": None,
        "affected_units": affected,
        "control": None,
        "control_requested": False,
        **extra,
    }


def _record(foreman: User, activity, *, detections, evaluated=60, no_presence=False, notes=""):
    return record_monitoring(
        foreman,
        activity.pk,
        {
            "done_date": today_in_bogota(),
            "sampling_unit": "trees",
            "evaluated_units": evaluated,
            "sampling_method": "zigzag",
            "notes": notes,
            "no_presence": no_presence,
            "detections": detections,
            "captured_at": None,
        },
    )


def _monitoring_history(foreman: User, plot: Plot, history_plot: Plot) -> list[str]:
    """Dos monitoreos del pasado: uno con una monilia que ya se atendió y una mazorca negra que
    espera su control (aparece en Sanidad), y otro sin presencia de plagas."""
    if PhytosanitaryMonitoring.objects.filter(activity__plot__farm=plot.farm).exists():
        return []
    owner = User.objects.get(producer=plot.farm.producer, groups__role__code="producer")
    controlled = _schedule(owner, history_plot, MONITORING, 0, foreman)
    treated = _detection(
        _pest("Monilia"),
        14,
        control={
            "id": uuid.uuid4(),
            "mode": "done",
            "method": "fruit_removal",
            "method_description": None,
            "inputs": [],
        },
    )
    waiting = _detection(_pest("Mazorca negra"), 6, control_requested=True)
    _record(
        foreman,
        controlled,
        detections=[treated, waiting],
        notes="Mazorcas con monilia en la zona baja; se retiraron ese día.",
    )
    _move_to(AgriculturalActivity.objects.get(pk=controlled.pk), 10)
    for activity_id in PhytosanitaryTreatment.objects.filter(
        detection__monitoring__activity=controlled
    ).values_list("activity_id", flat=True):
        _move_to(AgriculturalActivity.objects.get(pk=activity_id), 10)

    clean = _schedule(owner, plot, MONITORING, 0, foreman)
    _record(foreman, clean, detections=[], no_presence=True, evaluated=50)
    _move_to(AgriculturalActivity.objects.get(pk=clean.pk), 20)
    return ["Monitoreos del pasado: con detecciones y control pendiente, y sin presencia"]


def _harvests_and_lots(owner: User, foreman: User, plot: Plot) -> list[str]:
    if Harvest.objects.filter(plot__farm=plot.farm).exists():
        return []
    variety = plot.characterization.plantings.order_by("planting_date").first().variety
    today = today_in_bogota()
    harvests = []
    for days_ago, kilos, collector in (
        (21, "180", foreman),
        (14, "240", foreman),
        (7, "150", owner),
    ):
        harvest, _ = create_harvest(
            owner,
            {
                "plot_id": plot.pk,
                "harvest_date": today - timedelta(days=days_ago),
                "green_weight_kg": Decimal(kilos),
                "variety_id": variety.pk,
                "collector_id": collector.pk,
                "captured_at": None,
            },
        )
        harvests.append(harvest)
    # Los dos primeros ya son lote; el último queda por conformar, como se hace en la demostración.
    for harvest in harvests[:2]:
        if not Lot.objects.filter(harvest=harvest).exists():
            create_lot(owner, {"harvest_id": harvest.pk})
    return ["Cosechas (tres) y lotes (dos)"]
