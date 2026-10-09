from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .inventory_serializers import (
    InputMovementCreateSerializer,
    InputMovementQuerySerializer,
    InputMovementResultSerializer,
    InputMovementSerializer,
    InputStockListSerializer,
    InputStockQuerySerializer,
    InputStockSerializer,
)
from .services import list_movements, list_stocks, register_movement


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las existencias de una finca, sin paginar y solo de los insumos que tienen "
            "movimientos en ella (los demás están «Sin movimientos»). Una finca ajena o que no "
            "existe devuelve la lista vacía. `quantity` es un decimal en texto, en la unidad del "
            "insumo, y puede ser negativo."
        ),
        parameters=[InputStockQuerySerializer],
        responses={200: InputStockListSerializer, **error_responses(400, 401, 403)},
    )
)
class InputStockViewSet(GenericViewSet):
    serializer_class = InputStockSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {"list": "inputs.view_agriculturalinput"}
    filter_backends = []
    pagination_class = None

    def list(self, request):
        query = InputStockQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        stocks = list_stocks(request.user, query.validated_data["farm"])
        return Response({"results": InputStockSerializer(stocks, many=True).data})


@extend_schema_view(
    list=extend_schema(
        description=(
            "Los movimientos de un insumo en una finca, del más nuevo al más viejo (por fecha "
            "del hecho y, a igual fecha, por hora de registro). `quantity` lleva el signo: "
            "positiva en las entradas, negativa en las salidas y la diferencia en los conteos."
        ),
        parameters=[InputMovementQuerySerializer],
        responses={200: InputMovementSerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Registra una entrada (`quantity` mayor que cero) o un conteo (`counted_quantity` "
            "mayor o igual a cero). Las salidas por actividad no se aceptan aquí. Reenviar el "
            "mismo `id` con el mismo contenido responde 200 con el movimiento ya registrado y "
            "no duplica; con otro contenido, 409 `movement_id_conflict`."
        ),
        request=InputMovementCreateSerializer,
        responses={
            200: InputMovementResultSerializer,
            201: InputMovementResultSerializer,
            **error_responses(400, 401, 403, 404, 409, 422),
        },
    ),
)
class InputMovementViewSet(GenericViewSet):
    serializer_class = InputMovementSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "inputs.view_agriculturalinput",
        "create": "inputs.manage_inputstock",
    }
    filter_backends = []

    def list(self, request):
        query = InputMovementQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        movements = list_movements(
            request.user, query.validated_data["input"], query.validated_data["farm"]
        )
        page = self.paginate_queryset(movements)
        return self.get_paginated_response(InputMovementSerializer(page, many=True).data)

    def create(self, request):
        serializer = InputMovementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        movement, stock, created = register_movement(request.user, dict(serializer.validated_data))
        body = {
            "movement": InputMovementSerializer(movement).data,
            "stock": InputStockSerializer(stock).data,
        }
        return Response(body, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
