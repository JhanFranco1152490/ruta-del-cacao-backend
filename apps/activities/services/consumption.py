"""Los insumos que gasta una labor realizada y su descuento del inventario de la finca.

Lo usan registrar la realización y crear un control fitosanitario ya realizado.
"""

from decimal import Decimal

from ..choices import ActivityType
from ..exceptions import InputInactive, InvalidActivity
from ..models import AgriculturalActivity, AgriculturalActivityInput

QUANTITY_PLACES = Decimal("0.001")

# El modelo del insumo se toma de la relación y no de su app: ninguna app importa de otra.
AgriculturalInput = AgriculturalActivityInput._meta.get_field("input").related_model


def sent_inputs(rows) -> dict:
    """`{id del insumo: cantidad}`, con la cantidad en tres decimales, como se guarda."""
    sent = {}
    for row in rows:
        input_id = str(row["input_id"])
        if input_id in sent:
            raise InvalidActivity("inputs", "Este insumo ya está en la lista.")
        quantity = Decimal(str(row["quantity"]))
        if quantity <= 0:
            raise InvalidActivity("inputs", "La cantidad debe ser mayor que cero.")
        sent[input_id] = quantity.quantize(QUANTITY_PLACES)
    return sent


def used_inputs(activity: AgriculturalActivity) -> dict:
    return {str(row.input_id): row.quantity for row in activity.inputs.all()}


def locked_inputs(producer_id, sent: dict) -> dict:
    """Los insumos enviados, bloqueados en orden de id (después de la finca y antes de sus
    existencias, el orden que también sigue el inventario), para no cruzarse con su
    desactivación ni con otra labor que gaste los mismos."""
    if not sent:
        return {}
    items = {
        str(item.pk): item
        for item in AgriculturalInput.objects.select_for_update()
        .filter(pk__in=sent.keys(), producer_id=producer_id)
        .order_by("pk")
    }
    if len(items) != len(sent):
        # Un 400 y no un 404: la cola leería un 404 como una actividad eliminada y descartaría el
        # registro. Así llega a la bandeja y la persona elige otro insumo.
        raise InvalidActivity("inputs", "El insumo no existe en el catálogo del productor.")
    inactive = sorted(input_id for input_id, item in items.items() if not item.is_active)
    if inactive:
        raise InputInactive(inactive)
    return items


def discount_inputs(activity: AgriculturalActivity, items: dict, sent: dict, actor) -> None:
    note = _note(activity)
    for input_id, quantity in sent.items():
        item = items[input_id]
        movement = item.record_consumption(
            activity.plot.farm, quantity, activity.done_date, note, actor
        )
        AgriculturalActivityInput.objects.create(
            activity=activity, input=item, quantity=quantity, stock_movement=movement
        )


def inputs_for_history(sent: dict) -> list[dict]:
    return [
        {"input_id": input_id, "quantity": f"{quantity:.3f}"}
        for input_id, quantity in sorted(sent.items())
    ]


def _note(activity: AgriculturalActivity) -> str:
    """De qué labor viene la salida, como la muestra el inventario: "Fertilización · P-03"."""
    if activity.activity_type == ActivityType.OTHER:
        task = activity.other_description
    else:
        task = ActivityType(activity.activity_type).label
    return f"{task} · {activity.plot.code}"
