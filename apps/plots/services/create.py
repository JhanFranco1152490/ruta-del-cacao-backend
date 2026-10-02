from django.db import IntegrityError, transaction

from apps.common.db import constraint_name

from ..exceptions import DuplicatePlotCode, PlotIdConflict
from ..models import Plot, PlotAuditEvent
from . import rules
from .audit import record_plot_audit_event
from .content import CODE_UNIQUE_CONSTRAINT, apply_boundary, matches, writable

# Lo que describe a la parcela, para decidir si un reenvío trae el mismo contenido.
CONTENT_FIELDS = ("code", "area_hectares", "boundary")


@transaction.atomic
def create_plot(actor, data: dict) -> tuple[Plot, bool]:
    """Registra una parcela en una finca del productor de la sesión. Devuelve `(parcela,
    creada)`.

    El cliente puede enviar el `id` que generó sin conexión. Reenviar el mismo `id` con el mismo
    contenido devuelve la parcela ya creada (`creada=False`), de modo que reintentar un envío
    cortado nunca duplica.
    """
    plot_id = data.get("id")
    if plot_id is not None and (existing := _existing(plot_id)) is not None:
        return _resent_plot(existing, actor, data), False

    farm = rules.lock_farm(actor, data["farm_id"])
    # Con la finca bloqueada, otra sincronización del mismo registro que llegó a la vez ya
    # terminó: si la creó, se responde como un reenvío.
    if plot_id is not None and (existing := _existing(plot_id)) is not None:
        return _resent_plot(existing, actor, data), False
    rules.ensure_farm_active(farm)

    plot = Plot(farm=farm, **writable(data))
    if plot_id is not None:
        plot.pk = plot_id
    plot.full_clean(exclude=["farm"], validate_unique=False, validate_constraints=False)
    boundary = apply_boundary(plot, data.get("boundary"))
    rules.check_available_area(farm, plot.area_hectares)
    if boundary is not None:
        rules.check_no_overlap(farm, boundary)

    try:
        with transaction.atomic():
            plot.save(force_insert=True)
    except IntegrityError as error:
        # El mismo `id` en otra finca no pasa por el mismo bloqueo: el choque llega como clave
        # primaria repetida.
        existing = _existing(plot.pk) if plot_id is not None else None
        if existing is not None:
            return _resent_plot(existing, actor, data), False
        if constraint_name(error) == CODE_UNIQUE_CONSTRAINT:
            raise DuplicatePlotCode() from None
        raise
    record_plot_audit_event(plot=plot, actor=actor, action=PlotAuditEvent.Action.CREATED)
    return plot, True


def _existing(plot_id) -> Plot | None:
    return Plot.objects.select_related("farm").filter(pk=plot_id).first()


def _resent_plot(existing: Plot, actor, data: dict) -> Plot:
    if existing.farm.producer_id != actor.producer_id:
        raise PlotIdConflict()
    # Con el mismo dueño, un contenido distinto suele ser un pendiente editado en el dispositivo
    # después de una creación cuya respuesta se perdió: el conflicto lleva la parcela del
    # servidor para que el cliente envíe esa edición con su versión.
    if str(data["farm_id"]) != str(existing.farm_id) or not matches(
        existing, data, CONTENT_FIELDS
    ):
        raise PlotIdConflict(existing)
    return existing
