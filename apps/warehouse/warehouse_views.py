from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleWarehouseVersion
from .request_serializers import (
    WarehouseCreateSerializer,
    WarehouseDeleteSerializer,
    WarehouseUpdateSerializer,
)
from .serializers import (
    WarehouseConflictErrorSerializer,
    WarehouseListQuerySerializer,
    WarehouseSerializer,
)
from .services.warehouse_queries import get_warehouse, list_warehouses
from .services.warehouses import create_warehouse, delete_warehouse, update_warehouse

VIEW = "warehouse.view_stock"
MANAGE = "warehouse.manage_warehouse"


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las bodegas de las fincas que la cuenta alcanza, paginadas, por finca y nombre. "
            "`search` busca una parte del nombre sin distinguir mayúsculas, tildes ni espacios."
        ),
        parameters=[
            WarehouseListQuerySerializer,
            OpenApiParameter("producer", str, description="Solo para la cuenta técnica."),
        ],
        responses={200: WarehouseSerializer(many=True), **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(responses={200: WarehouseSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Registra una bodega en una finca que la cuenta alcanza; queda activa. Si ya hay una "
            "con el mismo nombre en la finca, 409 `warehouse_name_taken` con la existente en "
            "`existing`. Una finca inactiva, 422 `farm_inactive`."
        ),
        request=WarehouseCreateSerializer,
        responses={
            201: WarehouseSerializer,
            409: WarehouseConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Cambia el nombre o activa y desactiva la bodega. Requiere `expected_version`; si la "
            "bodega cambió, 409 `stale_version` con la vigente en `current`. La finca no se "
            "edita. Una bodega desactivada no recibe ingresos, pero lo que tiene sigue "
            "consultándose y admite salidas."
        ),
        request=WarehouseUpdateSerializer,
        responses={
            200: WarehouseSerializer,
            409: WarehouseConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina una bodega registrada por error. Requiere `expected_version` en la URL. Si "
            "ya recibió un ingreso, 409 `warehouse_has_records` (se desactiva en su lugar). Su "
            "historial se conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version", int, required=True, description="La `version` leída."
            )
        ],
        responses={
            204: None,
            409: WarehouseConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class WarehouseViewSet(GenericViewSet):
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "partial_update": MANAGE,
        "destroy": MANAGE,
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = WarehouseListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_warehouses(request.user, query.validated_data))
        return self.get_paginated_response(WarehouseSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(WarehouseSerializer(get_warehouse(request.user, pk)).data)

    def create(self, request):
        serializer = WarehouseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        warehouse = create_warehouse(request.user, serializer.validated_data)
        return Response(
            WarehouseSerializer(warehouse).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("warehouse-detail", args=[warehouse.pk])},
        )

    def partial_update(self, request, pk):
        serializer = WarehouseUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        return Response(
            WarehouseSerializer(update_warehouse(request.user, pk, expected_version, data)).data
        )

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP.
        serializer = WarehouseDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_warehouse(request.user, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        if isinstance(exc, StaleWarehouseVersion):
            exc.extra = {"current": WarehouseSerializer(exc.current_warehouse).data}
        return super().handle_exception(exc)
