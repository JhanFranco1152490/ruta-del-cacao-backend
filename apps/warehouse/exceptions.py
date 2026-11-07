from rest_framework import status

from apps.common.exceptions import ApiError


class WarehouseNotFound(ApiError):
    # También cubre la bodega de otro productor o de una finca fuera del alcance: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La bodega no existe."
    default_code = "not_found"


class StockLotNotFound(ApiError):
    # También cubre el lote que todavía no está Clasificado, el de otro productor y el de una finca
    # fuera del alcance.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El lote no existe."
    default_code = "not_found"


class StockExitNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La salida no existe."
    default_code = "not_found"


class FarmNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"


class FarmRequired(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Tu cuenta no tiene una finca asignada."
    default_code = "permission_denied"


class FarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La finca está inactiva: no se le pueden registrar bodegas."
    default_code = "farm_inactive"


class WarehouseNameTaken(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya existe una bodega con este nombre en la finca."
    default_code = "warehouse_name_taken"

    def __init__(self, existing=None):
        # La existente permite a la interfaz ofrecer verla o, si está inactiva, activarla.
        extra = None
        if existing is not None:
            extra = {
                "existing": {
                    "id": str(existing.pk),
                    "name": existing.name,
                    "is_active": existing.is_active,
                }
            }
        super().__init__(fields={"name": [self.default_detail]}, extra=extra)


class WarehouseHasRecords(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La bodega ya recibió ingresos: no se puede eliminar. Desactívala."
    default_code = "warehouse_has_records"


class StaleWarehouseVersion(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió esta bodega. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, current_warehouse):
        super().__init__()
        self.current_warehouse = current_warehouse


class StaleStockVersion(ApiError):
    # La versión del lote (al ingresar) o la del ingreso (al corregirlo) cambió desde que se leyó.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Otra persona cambió este lote. Revisa los datos actuales antes de guardar."
    default_code = "stale_version"

    def __init__(self, lot_id):
        # La vista envía el vigente en `current` para que el formulario cargue sus valores.
        super().__init__()
        self.lot_id = lot_id


class LotInvalidStatus(ApiError):
    # El mismo código que responde la cadena de estados del lote cuando se le pide un paso que no
    # le toca: el cliente lo trata igual venga de donde venga.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El lote no está en el estado que esta operación necesita."
    default_code = "lot_invalid_status"

    def __init__(self, current_status: str):
        super().__init__(extra={"current_status": current_status})


class LotNothingToStore(ApiError):
    # Un lote cuyo peso seco se fue entero en descarte parcial no tiene kilos de G1 ni de G2.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El lote no tiene kilos de G1 ni de G2 para ingresar."
    default_code = "lot_nothing_to_store"


class WarehouseFarmMismatch(ApiError):
    # El cacao se guarda en la finca donde se cosechó.
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La bodega es de otra finca: el lote solo puede ingresar a las de su finca."
    default_code = "warehouse_farm_mismatch"

    def __init__(self):
        super().__init__(fields={"warehouse_id": [self.default_detail]})


class WarehouseInactive(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "La bodega está desactivada: no recibe ingresos."
    default_code = "warehouse_inactive"

    def __init__(self):
        super().__init__(fields={"warehouse_id": [self.default_detail]})


class EntryHasMovements(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Ya salió cacao de este lote: el ingreso no se puede corregir."
    default_code = "entry_has_movements"


class StockInsufficient(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "stock_insufficient"

    def __init__(self, available):
        message = f"La cantidad supera lo disponible ({available:.1f} kg)".replace(".", ",")
        super().__init__(
            message,
            fields={"quantity_kg": [message]},
            extra={"available_kg": f"{available:.1f}"},
        )


class ExitAlreadyVoided(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "La salida ya está anulada."
    default_code = "exit_already_voided"


class ExitNotVoidable(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Una salida por venta se anula desde la venta."
    default_code = "exit_not_voidable"
