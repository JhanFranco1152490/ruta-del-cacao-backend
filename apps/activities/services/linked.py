"""Lo que otra app hace sobre una actividad: sanidad cierra un monitoreo cuando registra su
resultado y crea los controles fitosanitarios que atienden una detección.

Se llega aquí por los métodos de `AgriculturalActivity`, como las actividades llegan al inventario
por `record_consumption`: así sanidad no importa nada de esta app. Quien llama ya tiene bloqueada
la finca de la parcela y decide antes si quien actúa puede hacerlo; aquí se aplican las reglas de
la actividad (fechas, responsable, insumos), su versión y su historial.
"""

from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.common.db import save_translating_unique

from ..choices import ActivityStatus, ActivityType
from ..exceptions import ActivityIdConflict
from ..models import AgriculturalActivity, AgriculturalActivityAuditEvent
from . import rules
from .audit import plan_values, record_activity_event
from .complete import ensure_valid_done_date, mark_done, record_completion
from .consumption import discount_inputs, locked_inputs, sent_inputs
from .create import ID_CONSTRAINT


@transaction.atomic
def complete_monitoring(activity: AgriculturalActivity, actor, done_date: date, captured_at):
    """Marca realizado un monitoreo programado, sin insumos: lo que se encontró lo guarda
    sanidad."""
    ensure_valid_done_date(done_date, not_before=timezone.localdate(activity.created_at))
    mark_done(activity, actor, done_date, captured_at)
    record_completion(activity, actor, {})


@transaction.atomic
def schedule_control(actor, plot, control_id, scheduled_date: date, assignee_id):
    """Programa un control fitosanitario con las reglas de programar cualquier labor."""
    rules.ensure_plot_open(plot)
    rules.ensure_not_past(scheduled_date)
    control = _new_control(
        control_id, plot, scheduled_date, rules.assignee_for(actor, plot, assignee_id)
    )
    _insert(control)
    _record_created(control, actor)
    return control


@transaction.atomic
def record_done_control(
    actor, plot, control_id, done_date: date, not_before: date, assignee_id, inputs, captured_at
):
    """Crea un control que ya se hizo y descuenta sus insumos del inventario de la finca.

    Como la labor ya ocurrió, una parcela o finca inactiva no lo impide. La fecha no puede ser
    futura ni anterior a `not_before`, el monitoreo que lo originó: la regla de la realización
    compara con el día en que se programó, que en un control que nace realizado es hoy.
    """
    sent = sent_inputs(inputs)
    ensure_valid_done_date(done_date, not_before=not_before)
    control = _new_control(
        control_id, plot, done_date, rules.assignee_for(actor, plot, assignee_id)
    )
    items = locked_inputs(plot.farm.producer_id, sent)
    _insert(control)
    _record_created(control, actor)
    mark_done(control, actor, done_date, captured_at)
    discount_inputs(control, items, sent, actor)
    record_completion(control, actor, sent)
    return control


def _new_control(control_id, plot, scheduled_date, assignee) -> AgriculturalActivity:
    return AgriculturalActivity(
        id=control_id,
        plot=plot,
        activity_type=ActivityType.PHYTOSANITARY_CONTROL,
        scheduled_date=scheduled_date,
        assignee=assignee,
        status=ActivityStatus.SCHEDULED,
    )


def _insert(control: AgriculturalActivity) -> None:
    # Un `id` que ya usa otra actividad. Si el reenvío es del mismo control, sanidad lo reconoce
    # antes de llegar aquí.
    save_translating_unique(
        lambda: control.save(force_insert=True),
        constraint=ID_CONSTRAINT,
        duplicate=ActivityIdConflict,
    )


def _record_created(control: AgriculturalActivity, actor) -> None:
    record_activity_event(
        activity=control,
        actor=actor,
        action=AgriculturalActivityAuditEvent.Action.CREATED,
        before={},
        after=plan_values(control),
    )
