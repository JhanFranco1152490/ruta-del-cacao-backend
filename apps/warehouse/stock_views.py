from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleStockVersion
from .request_serializers import (
    EntryCreateSerializer,
    EntryUpdateSerializer,
    ExitCreateSerializer,
    ExitVoidSerializer,
    MoveCreateSerializer,
)
from .serializers import (
    ExitListQuerySerializer,
    ExitSummaryQuerySerializer,
    ExitSummarySerializer,
    LotStockSerializer,
    PendingEntryQuerySerializer,
    PendingEntrySerializer,
    StockConflictErrorSerializer,
    StockExitRowSerializer,
    StockInsufficientErrorSerializer,
    StockListQuerySerializer,
    StockLocationsQuerySerializer,
    StockLocationsSerializer,
    StockRowSerializer,
    StockSummaryQuerySerializer,
    StockSummarySerializer,
)
from .services.entry import correct_entry, register_entry
from .services.exits import register_exit, void_exit
from .services.moves import move_stock
from .services.stock_queries import (
    exit_summary,
    get_lot_stock,
    list_exits,
    list_stock,
    pending_entry_lots,
    stock_locations,
    stock_summary,
)

VIEW = "warehouse.view_stock"
REGISTER_ENTRY = "warehouse.register_entry"
REGISTER_EXIT = "warehouse.register_exit"
PRODUCER_PARAMETER = OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las existencias disponibles de las fincas que la cuenta alcanza, una fila por lote y "
            "calibre con más de 0 kg. Los filtros se combinan; `location` y `search` buscan una "
            "parte del texto sin distinguir mayúsculas. `ordering` es uno de `lot`, `grade`, "
            "`quantity`, `location` o `entry_date`, con `-` para el orden inverso; por defecto, "
            "el ingreso más reciente."
        ),
        parameters=[StockListQuerySerializer, PRODUCER_PARAMETER],
        responses={200: StockRowSerializer(many=True), **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        description=(
            "El ingreso, las existencias por calibre y las salidas de un lote Clasificado o En "
            "bodega. Un lote en otro estado es 404."
        ),
        responses={200: LotStockSerializer, **error_responses(401, 403, 404)},
    ),
)
class StockViewSet(GenericViewSet):
    serializer_class = LotStockSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": VIEW,
        "summary": VIEW,
        "locations": VIEW,
        "exit_history": VIEW,
        "exit_summary": VIEW,
        "retrieve": VIEW,
        "pending_entry": REGISTER_ENTRY,
        "entry": REGISTER_ENTRY,
        "correct_entry": REGISTER_ENTRY,
        "move": REGISTER_ENTRY,
        "exits": REGISTER_EXIT,
        "void_exit": REGISTER_EXIT,
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = StockListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_stock(request.user, query.validated_data))
        return self.get_paginated_response(StockRowSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(LotStockSerializer(get_lot_stock(request.user, pk)).data)

    @extend_schema(
        description=(
            "Los totales de la pantalla: los kilos disponibles de G1 y de G2 y cuántos lotes "
            "tienen existencias, entre las filas que cumplen los mismos filtros de la lista."
        ),
        parameters=[StockSummaryQuerySerializer, PRODUCER_PARAMETER],
        responses={200: StockSummarySerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        query = StockSummaryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(
            StockSummarySerializer(stock_summary(request.user, query.validated_data)).data
        )

    @extend_schema(
        description=(
            "Las ubicaciones con existencias en una bodega, sin repetir y en orden alfabético: "
            "alimentan el filtro y las sugerencias del formulario de ingreso."
        ),
        parameters=[StockLocationsQuerySerializer],
        responses={200: StockLocationsSerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def locations(self, request):
        query = StockLocationsQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        locations = stock_locations(request.user, query.validated_data["warehouse"])
        return Response({"results": locations})

    @extend_schema(
        description=(
            "Las salidas de cacao de las fincas que la cuenta alcanza, la más reciente primero, "
            "con las anuladas (`voided`) incluidas salvo que `state` pida solo las vigentes o "
            "solo las anuladas. `warehouse` es la bodega donde está hoy el cacao del lote; "
            "`date_from` y `date_to` acotan la fecha de la salida, ambas incluidas."
        ),
        parameters=[ExitListQuerySerializer, PRODUCER_PARAMETER],
        responses={200: StockExitRowSerializer(many=True), **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], url_path="exits", url_name="exit-list")
    def exit_history(self, request):
        query = ExitListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_exits(request.user, query.validated_data))
        return self.get_paginated_response(StockExitRowSerializer(page, many=True).data)

    @extend_schema(
        description=(
            "Lo que salió con los mismos filtros de la lista de salidas (menos `state`): el total "
            "de salidas y de kilos vigentes, y los de cada motivo, de los que más kilos sacaron a "
            "los que menos. Lo anulado no cuenta."
        ),
        parameters=[ExitSummaryQuerySerializer, PRODUCER_PARAMETER],
        responses={200: ExitSummarySerializer, **error_responses(400, 401, 403)},
    )
    @action(
        detail=False,
        methods=["get"],
        url_path="exits/summary",
        url_name="exit-summary",
        pagination_class=None,
    )
    def exit_summary(self, request):
        query = ExitSummaryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(
            ExitSummarySerializer(exit_summary(request.user, query.validated_data)).data
        )

    @extend_schema(
        description=(
            "Los lotes Clasificado por ingresar a bodega, del que se clasificó primero. Un lote "
            "sin kilos de G1 ni de G2 no aparece."
        ),
        parameters=[PendingEntryQuerySerializer, PRODUCER_PARAMETER],
        responses={200: PendingEntrySerializer(many=True), **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], url_path="pending-entry")
    def pending_entry(self, request):
        query = PendingEntryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(pending_entry_lots(request.user, query.validated_data))
        return self.get_paginated_response(PendingEntrySerializer(page, many=True).data)

    @extend_schema(
        description=(
            "Ingresa un lote Clasificado a una bodega de su finca, con la fecha y la ubicación. "
            "Los kilos de G1 y de G2 son los de su clasificación. El lote pasa a En bodega. "
            "Requiere `expected_lot_version`; en otro estado, 409 `lot_invalid_status` con "
            "`current_status`. Un lote sin kilos que ingresar, 409 `lot_nothing_to_store`."
        ),
        request=EntryCreateSerializer,
        responses={
            201: LotStockSerializer,
            409: StockConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @action(detail=True, methods=["post"])
    def entry(self, request, pk):
        serializer = EntryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        register_entry(request.user, pk, serializer.validated_data)
        return Response(
            LotStockSerializer(get_lot_stock(request.user, pk)).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("stock-detail", args=[pk])},
        )

    @extend_schema(
        description=(
            "Corrige la fecha, la bodega o la ubicación de un ingreso, y las existencias con él. "
            "Los kilos no se corrigen. Solo mientras no haya salido nada del lote: con una salida "
            "en vigor, 409 `entry_has_movements`. Requiere `expected_version` del ingreso; si "
            "cambió, 409 `stale_version` con el lote vigente en `current`."
        ),
        request=EntryUpdateSerializer,
        responses={
            200: LotStockSerializer,
            409: StockConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @entry.mapping.patch
    def correct_entry(self, request, pk):
        serializer = EntryUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        correct_entry(request.user, pk, expected_version, data)
        return Response(LotStockSerializer(get_lot_stock(request.user, pk)).data)

    @extend_schema(
        description=(
            "Mueve el cacao de un lote En bodega a otra bodega de su finca o a otra ubicación, "
            "en cualquier momento y con las existencias que tenga. Deja de dónde venía. Requiere "
            "`expected_version` del ingreso; si cambió, 409 `stale_version`. Sin cacao en "
            "bodega, 409 `lot_without_stock`; al mismo lugar, 400 `stock_move_unchanged`."
        ),
        request=MoveCreateSerializer,
        responses={
            201: LotStockSerializer,
            409: StockConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @action(detail=True, methods=["post"])
    def move(self, request, pk):
        serializer = MoveCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        move_stock(
            request.user,
            pk,
            data.pop("expected_version"),
            warehouse_id=data["warehouse_id"],
            location=data["location"],
        )
        return Response(
            LotStockSerializer(get_lot_stock(request.user, pk)).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("stock-detail", args=[pk])},
        )

    @extend_schema(
        description=(
            "Registra la salida de un calibre de un lote En bodega, con su fecha y su motivo "
            "(Venta no se elige: la genera la venta). La cantidad no puede superar lo disponible "
            "del calibre: si no, 400 `stock_insufficient` con `available_kg`. La salida queda a "
            "nombre de quien la registra. En otro estado, 409 `lot_invalid_status`."
        ),
        request=ExitCreateSerializer,
        responses={
            201: LotStockSerializer,
            400: StockInsufficientErrorSerializer,
            409: StockConflictErrorSerializer,
            **error_responses(401, 403, 404),
        },
    )
    @action(detail=True, methods=["post"])
    def exits(self, request, pk):
        serializer = ExitCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        register_exit(request.user, pk, serializer.validated_data)
        return Response(
            LotStockSerializer(get_lot_stock(request.user, pk)).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("stock-detail", args=[pk])},
        )

    @extend_schema(
        description=(
            "Anula una salida manual: los kilos vuelven a la existencia y la salida queda en el "
            "historial con quién la anuló y por qué. Una salida ya anulada es 409 "
            "`exit_already_voided`; una por venta, 409 `exit_not_voidable`."
        ),
        request=ExitVoidSerializer,
        responses={
            200: LotStockSerializer,
            409: StockConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="exits/<uuid:exit_id>/void",
        url_name="void-exit",
    )
    def void_exit(self, request, pk, exit_id):
        serializer = ExitVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        void_exit(request.user, pk, exit_id, serializer.validated_data["reason"])
        return Response(LotStockSerializer(get_lot_stock(request.user, pk)).data)

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con el lote; aquí se arma lo que el formulario necesita
        # para cargar los valores vigentes sin otra consulta.
        if isinstance(exc, StaleStockVersion):
            current = get_lot_stock(self.request.user, exc.lot_id)
            exc.extra = {"current": LotStockSerializer(current).data}
        return super().handle_exception(exc)
