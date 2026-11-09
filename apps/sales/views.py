from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import (
    SaleListItemSerializer,
    SaleListQuerySerializer,
    SaleSerializer,
    SaleSummaryQuerySerializer,
    SaleSummarySerializer,
)
from .services import get_sale, list_sales, sales_summary

VIEW = "sales.view_sale"
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
)
class SaleViewSet(GenericViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": VIEW,
        "summary": VIEW,
        "retrieve": VIEW,
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
