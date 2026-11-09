from rest_framework import status

from apps.common.exceptions import ApiError


class SaleNotFound(ApiError):
    # También cubre la venta de otro productor o de una finca que la cuenta no alcanza: responder
    # distinto confirmaría que existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La venta no existe."
    default_code = "not_found"


class SaleFarmNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "La finca no existe."
    default_code = "not_found"

    def __init__(self):
        super().__init__(fields={"farm_id": [self.default_detail]})


class SaleFarmInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "La finca está inactiva: no se le pueden registrar ventas."
    default_code = "farm_inactive"

    def __init__(self):
        super().__init__(fields={"farm_id": [self.default_detail]})


class SaleBuyerNotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El comprador no existe."
    default_code = "not_found"

    def __init__(self):
        super().__init__(fields={"buyer_id": [self.default_detail]})


class BuyerInactive(ApiError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "El comprador está inactivo: actívalo para venderle."
    default_code = "buyer_inactive"

    def __init__(self):
        super().__init__(fields={"buyer_id": [self.default_detail]})


# Los errores de una línea dicen cuál es en `line` (desde 0), para que el formulario la marque.


class SaleLotNotFound(ApiError):
    # Un lote de otra finca que la de la venta responde lo mismo que uno que no existe.
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "El lote no existe en la finca de la venta."
    default_code = "not_found"

    def __init__(self, line: int):
        super().__init__(fields={"lines": [self.default_detail]}, extra={"line": line})


class SaleLotInvalidStatus(ApiError):
    # El mismo código de la cadena de estados del lote: el cliente lo trata igual.
    status_code = status.HTTP_409_CONFLICT
    default_detail = "El lote no está En bodega."
    default_code = "lot_invalid_status"

    def __init__(self, line: int, current_status: str):
        super().__init__(
            fields={"lines": [self.default_detail]},
            extra={"line": line, "current_status": current_status},
        )


class SaleStockInsufficient(ApiError):
    # El mismo código y mensaje de bodega, con la línea que lo pide.
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "stock_insufficient"

    def __init__(self, line: int, available):
        message = f"La cantidad supera lo disponible ({available:.1f} kg)".replace(".", ",")
        super().__init__(
            message,
            fields={"lines": [message]},
            extra={"line": line, "available_kg": f"{available:.1f}"},
        )
