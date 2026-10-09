"""Registro de movimientos de inventario.

Todo movimiento pasa por aquí, en una transacción que bloquea siempre en el mismo orden: la
finca, el insumo y sus existencias. Con ese orden fijo (que también siguen las actividades al
descontar lo que gastan) dos operaciones sobre el mismo insumo y finca nunca se esperan entre sí.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.common.locks import lock_root_row
from apps.common.ownership import owner_filter

from ..exceptions import (
    FarmInactive,
    FarmNotFound,
    InputInactive,
    InputNotFound,
    MovementIdConflict,
)
from ..models import (
    NOTE_MAX_LENGTH,
    QUANTITY_MAX,
    AgriculturalInput,
    InputMovement,
    InputStock,
)

Kind = InputMovement.Kind
# Lo que una persona puede registrar: las salidas las registra el sistema desde las actividades.
MANUAL_KINDS = (Kind.ENTRY, Kind.COUNT)


def _farm_model():
    # El modelo se toma de la relación y no de su app: ninguna app importa de otra.
    return InputMovement._meta.get_field("farm").related_model


@transaction.atomic
def register_movement(actor, data: dict) -> tuple[InputMovement, InputStock, bool]:
    """Registra una entrada o un conteo y devuelve `(movimiento, existencias, creado)`.

    Si llega un `id` que ya existe con el mismo contenido (un doble clic o una respuesta perdida)
    devuelve el movimiento ya registrado con `creado=False`, sin duplicarlo ni tocar las
    existencias. Con otro contenido, `MovementIdConflict`.
    """
    farm_model = _farm_model()
    item = AgriculturalInput.objects.filter(pk=data["input_id"], **owner_filter(actor)).first()
    if item is None:
        raise InputNotFound()
    farm = farm_model.objects.filter(pk=data["farm_id"], **owner_filter(actor)).first()
    if farm is None:
        raise FarmNotFound()
    if item.producer_id != farm.producer_id:
        raise ValidationError({"farm_id": ["La finca no es del productor del insumo."]})

    _validate(data)
    # Con los bloqueos tomados se vuelven a leer: lo que se decide es lo que nadie más puede
    # cambiar hasta el final de la transacción.
    farm = _lock_farm(farm.pk)
    item = _lock_input(item.pk)
    stock = _locked_stock(item, farm)

    movement_id = data.get("id")
    if movement_id is not None:
        existing = InputMovement.objects.filter(pk=movement_id).first()
        if existing is not None:
            return _resent(existing, item, farm, data), stock, False

    if not farm.is_active:
        raise FarmInactive()
    if data["kind"] == Kind.ENTRY and not item.is_active:
        raise InputInactive()

    if data["kind"] == Kind.ENTRY:
        movement = _apply(
            stock,
            kind=Kind.ENTRY,
            quantity=data["quantity"],
            counted_quantity=None,
            occurred_on=data["occurred_on"],
            note=data.get("note", ""),
            actor=actor,
            movement_id=movement_id,
        )
    else:
        counted = data["counted_quantity"]
        movement = _apply(
            stock,
            kind=Kind.COUNT,
            # La diferencia se calcula contra las existencias de este momento: el conteo deja
            # lo que hay en la bodega aunque entretanto haya llegado una salida.
            quantity=counted - stock.quantity,
            counted_quantity=counted,
            occurred_on=data["occurred_on"],
            note=data.get("note", ""),
            actor=actor,
            movement_id=movement_id,
        )
    return movement, stock, True


@transaction.atomic
def record_consumption(item, farm, quantity, occurred_on, note, actor) -> InputMovement:
    """Descuenta `quantity` (en positivo) de las existencias de `farm`. Ver
    `AgriculturalInput.record_consumption`."""
    if quantity <= 0:
        raise ValueError("The consumed quantity must be greater than zero.")
    farm = _lock_farm(farm.pk)
    item = _lock_input(item.pk)
    stock = _locked_stock(item, farm)
    return _apply(
        stock,
        kind=Kind.CONSUMPTION,
        quantity=-quantity,
        counted_quantity=None,
        occurred_on=occurred_on,
        note=note,
        actor=actor,
    )


def _apply(
    stock: InputStock,
    *,
    kind,
    quantity,
    counted_quantity,
    occurred_on,
    note,
    actor,
    movement_id=None,
) -> InputMovement:
    """Crea el movimiento y lo suma a las existencias, ya bloqueadas."""
    extra = {} if movement_id is None else {"id": movement_id}
    movement = InputMovement.objects.create(
        input_id=stock.input_id,
        farm_id=stock.farm_id,
        kind=kind,
        quantity=quantity,
        counted_quantity=counted_quantity,
        occurred_on=occurred_on,
        note=note,
        actor=actor,
        **extra,
    )
    stock.quantity += quantity
    fields = ["quantity", "updated_at"]
    if kind == Kind.COUNT and (
        stock.last_count_date is None or occurred_on > stock.last_count_date
    ):
        # Un conteo de una fecha anterior no hace retroceder el último conteo.
        stock.last_count_date = occurred_on
        fields.append("last_count_date")
    stock.save(update_fields=fields)
    return movement


def _lock_farm(farm_id):
    farm = lock_root_row(_farm_model(), farm_id)
    if farm is None:
        raise FarmNotFound()
    return farm


def _lock_input(input_id) -> AgriculturalInput:
    item = AgriculturalInput.objects.select_for_update().filter(pk=input_id).first()
    if item is None:
        raise InputNotFound()
    return item


def _locked_stock(item, farm) -> InputStock:
    stock = InputStock.objects.select_for_update().filter(input=item, farm=farm).first()
    if stock is None:
        # Dos filas nuevas a la vez no pueden pasar: todo movimiento bloquea antes la finca.
        stock = InputStock.objects.create(input=item, farm=farm, quantity=Decimal("0"))
    return stock


def _resent(existing, item, farm, data) -> InputMovement:
    same = (
        existing.input_id == item.pk
        and existing.farm_id == farm.pk
        and existing.kind == data["kind"]
        and existing.occurred_on == data["occurred_on"]
        and existing.note == data.get("note", "")
    )
    if same and data["kind"] == Kind.ENTRY:
        same = existing.quantity == data["quantity"]
    elif same:
        same = existing.counted_quantity == data["counted_quantity"]
    if not same:
        raise MovementIdConflict()
    return existing


def _validate(data: dict) -> None:
    """Las reglas del movimiento, también para quien llame sin pasar por la API."""
    kind = data.get("kind")
    if kind not in MANUAL_KINDS:
        raise ValidationError({"kind": ["Solo se registran entradas y conteos."]})
    field = "quantity" if kind == Kind.ENTRY else "counted_quantity"
    other = "counted_quantity" if kind == Kind.ENTRY else "quantity"
    errors = {}
    value = data.get(field)
    if value is None:
        errors[field] = ["Este campo es requerido."]
    elif kind == Kind.ENTRY and value <= 0:
        errors[field] = ["La cantidad debe ser mayor que cero."]
    elif kind == Kind.COUNT and value < 0:
        errors[field] = ["La cantidad contada no puede ser negativa."]
    elif value > QUANTITY_MAX:
        errors[field] = ["La cantidad es demasiado grande."]
    if data.get(other) is not None:
        errors[other] = ["Campo no permitido para este tipo de movimiento."]
    if data["occurred_on"] > timezone.localdate():
        errors["occurred_on"] = ["La fecha no puede ser futura."]
    if len(data.get("note", "")) > NOTE_MAX_LENGTH:
        errors["note"] = [f"La nota no puede pasar de {NOTE_MAX_LENGTH} caracteres."]
    if errors:
        raise ValidationError(errors)
