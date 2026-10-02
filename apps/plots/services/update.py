from django.db import IntegrityError, transaction

from apps.common.db import constraint_name

from ..exceptions import DuplicatePlotCode, PlotNotFound, StalePlotVersion
from ..models import Plot, PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event
from .content import (
    CODE_UNIQUE_CONSTRAINT,
    UPDATABLE_FIELDS,
    apply_boundary,
    check_declared_area,
    current_boundary,
    matches,
)


@transaction.atomic
def update_plot(actor, plot_id, expected_version: int, data: dict) -> Plot:
    """Edita, desactiva o reactiva una parcela. `boundary` reemplaza el contorno completo, y
    `None` lo quita.

    Las reglas de área y de superposición se revisan de nuevo solo si la parcela queda activa y
    cambia lo que ellas miran: su área, su contorno, o su estado al reactivarla. Desactivar no
    revisa nada, porque solo libera área.
    """
    farm_id = (
        Plot.objects.filter(pk=plot_id, farm__producer_id=actor.producer_id)
        .values_list("farm_id", flat=True)
        .first()
    )
    if farm_id is None:
        raise PlotNotFound()
    # Siempre la finca antes que la parcela, en el mismo orden que el alta: dos operaciones que
    # toman los mismos bloqueos en orden distinto pueden quedar esperándose una a la otra.
    farm = rules.lock_farm(actor, farm_id)
    plot = Plot.objects.select_for_update().select_related("farm").get(pk=plot_id)
    if plot.version != expected_version:
        # Una cola sin conexión reintenta cuando no recibió la respuesta, aunque el servidor sí
        # haya aplicado el cambio: si la parcela ya tiene justo lo que se pide, es un éxito.
        if matches(plot, data, data.keys()):
            return plot
        raise StalePlotVersion(plot)
    rules.ensure_farm_active(farm)

    before = {name: getattr(plot, name) for name in (*UPDATABLE_FIELDS, "boundary")}
    for name in UPDATABLE_FIELDS:
        if name in data:
            setattr(plot, name, data[name])
    plot.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    if "boundary" in data:
        boundary = apply_boundary(plot, data["boundary"])
    else:
        boundary = current_boundary(plot)
        if boundary is not None and plot.area_hectares != before["area_hectares"]:
            check_declared_area(plot, plot.measured_area_hectares)
    # Se compara después de validar: un código que solo cambió en espacios no es un cambio.
    changed = [name for name in before if getattr(plot, name) != before[name]]
    if not changed:
        return plot

    reactivated = "is_active" in changed and plot.is_active
    if plot.is_active and (reactivated or "area_hectares" in changed):
        rules.check_available_area(farm, plot.area_hectares, exclude_plot_id=plot.pk)
    if plot.is_active and boundary is not None and (reactivated or "boundary" in changed):
        rules.check_no_overlap(farm, boundary, exclude_plot_id=plot.pk)

    plot.version += 1
    update_fields = [*changed, "version", "updated_at"]
    if "code" in changed:
        update_fields.append("code_normalized")
    if "boundary" in changed:
        update_fields.append("measured_area_hectares")
    try:
        with transaction.atomic():
            plot.save(update_fields=update_fields)
    except IntegrityError as error:
        if constraint_name(error) == CODE_UNIQUE_CONSTRAINT:
            raise DuplicatePlotCode() from None
        raise

    content_changes = [name for name in changed if name != "is_active"]
    if content_changes:
        record_plot_audit_event(
            plot=plot,
            actor=actor,
            action=PlotAuditEvent.Action.UPDATED,
            changed_fields=content_changes,
        )
    if "is_active" in changed:
        record_plot_audit_event(
            plot=plot,
            actor=actor,
            action=PlotAuditEvent.Action.STATUS_CHANGED,
            changed_fields=["is_active"],
        )
    return plot
