from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleSaleVersion
from .request_serializers import (
    BuyerOptionsQuerySerializer,
    SaleCreateSerializer,
    SaleVoidRequestSerializer,
)
from .serializers import (
    BuyerOptionListSerializer,
    BuyerOptionSerializer,
    SaleConflictErrorSerializer,
    SaleListItemSerializer,
    SaleListQuerySerializer,
    SaleSerializer,
    SaleSummaryQuerySerializer,
    SaleSummarySerializer,
)
from .services import (
    buyer_options,
    create_sale,
    get_sale,
    list_sales,
    sales_summary,
    void_sale,
)

VIEW = "sales.view_sale"
ADD = "sales.add_sale"
VOID = "sales.void_sale"
PRODUCER_PARAMETER = OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las ventas del periodo, `from` y `to` incluidos, de hasta 366 días, de las fincas "
            "que la cuenta alcanza; de la más reciente a la más antigua. Sin sus líneas: con los "
            "kilos de G1 y G2 y el total. `status` es `registered` o `voided` (sin él, las dos), "
            "y `search` busca por el número (`V-0012`, `12`)."
        ),
        parameters=[SaleListQuerySerializer, PRODUCER_PARAMETER],
        responses={200: SaleListItemSerializer(many=True), **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        description="Una venta con sus líneas, su soporte y, si se anuló, quién y por qué.",
        responses={200: SaleSerializer, **error_responses(401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Registra la venta de los lotes En bodega de una finca a un comprador activo del "
            "mismo productor. Cada línea (lote y calibre, sin repetir) saca sus kilos de la "
            "bodega con motivo Venta, en la misma transacción: si una pide más de lo que hay, "
            "400 `stock_insufficient` con `line` (desde 0) y `available_kg`, y no queda nada. "
            "Un lote de otra finca es 404 y uno que no está En bodega, 409 "
            "`lot_invalid_status`, los dos con `line`. El subtotal de cada línea es kilos por "
            "precio, redondeado al peso; el número (`V-0012`) lo asigna el servidor."
        ),
        request=SaleCreateSerializer,
        responses={201: SaleSerializer, **error_responses(400, 401, 403, 404, 409, 422)},
    ),
)
class SaleViewSet(GenericViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": VIEW,
        "summary": VIEW,
        "retrieve": VIEW,
        "create": ADD,
        "buyer_options": ADD,
        "void": VOID,
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = SaleListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_sales(request.user, query.validated_data))
        return self.get_paginated_response(SaleListItemSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(SaleSerializer(get_sale(request.user, pk)).data)

    @extend_schema(
        description=(
            "Las cifras de la pantalla: el valor vendido, los kilos de G1 y G2 y cuántas ventas, "
            "con los mismos filtros de la lista. Solo cuentan las ventas registradas."
        ),
        parameters=[SaleSummaryQuerySerializer, PRODUCER_PARAMETER],
        responses={200: SaleSummarySerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        query = SaleSummaryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(
            SaleSummarySerializer(sales_summary(request.user, query.validated_data)).data
        )

    def create(self, request):
        serializer = SaleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sale = create_sale(request.user, serializer.validated_data)
        return Response(
            SaleSerializer(sale).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("sale-detail", args=[sale.pk])},
        )

    @extend_schema(
        description=(
            "Los compradores activos a los que se les puede vender, para el formulario: "
            "solo su nombre y su tipo. La cuenta técnica nombra el productor."
        ),
        parameters=[PRODUCER_PARAMETER],
        responses={200: BuyerOptionListSerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], url_path="buyer-options", pagination_class=None)
    def buyer_options(self, request):
        query = BuyerOptionsQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        buyers = buyer_options(request.user, producer=query.validated_data.get("producer"))
        return Response({"results": BuyerOptionSerializer(buyers, many=True).data})

    @extend_schema(
        description=(
            "Anula la venta con su motivo: los kilos de cada línea vuelven a la bodega y sus "
            "salidas quedan anuladas, en la misma transacción. Requiere `expected_version`; si "
            "la venta cambió, 409 `stale_version` con la vigente en `current`. Una venta "
            "anulada no se vuelve a anular (409 `sale_voided`) ni se reactiva."
        ),
        request=SaleVoidRequestSerializer,
        responses={
            200: SaleSerializer,
            409: SaleConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @action(detail=True, methods=["post"])
    def void(self, request, pk):
        serializer = SaleVoidRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sale = void_sale(request.user, pk, data["expected_version"], data["reason"])
        return Response(SaleSerializer(sale).data)

    def handle_exception(self, exc):
        if isinstance(exc, StaleSaleVersion):
            exc.extra = {"current": SaleSerializer(exc.current_sale).data}
        return super().handle_exception(exc)
