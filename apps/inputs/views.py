from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleInputVersion
from .serializers import (
    AgriculturalInputConflictErrorSerializer,
    AgriculturalInputCreateSerializer,
    AgriculturalInputDeleteSerializer,
    AgriculturalInputListQuerySerializer,
    AgriculturalInputListSerializer,
    AgriculturalInputSerializer,
    AgriculturalInputUpdateSerializer,
)
from .services import create_input, delete_input, get_input, list_inputs, update_input


@extend_schema_view(
    list=extend_schema(
        description=(
            "El catálogo completo del productor de la sesión, activos e inactivos, ordenado por "
            "nombre y sin paginar: la búsqueda y los filtros corren en el dispositivo."
        ),
        parameters=[
            OpenApiParameter(
                "producer",
                OpenApiTypes.UUID,
                description="Solo la cuenta técnica: el productor cuyo catálogo se quiere ver.",
            )
        ],
        responses={200: AgriculturalInputListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        responses={200: AgriculturalInputSerializer, **error_responses(401, 403, 404)}
    ),
    create=extend_schema(
        description=(
            "Registra un insumo en el catálogo del productor de la sesión. `producer_id` solo "
            "lo envía la cuenta técnica, y para ella es obligatorio. Si ya existe uno con el "
            "mismo nombre y tipo, 409 `duplicate_input` con el existente en `existing`."
        ),
        request=AgriculturalInputCreateSerializer,
        responses={
            201: AgriculturalInputSerializer,
            409: AgriculturalInputConflictErrorSerializer,
            **error_responses(400, 401, 403, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edición parcial, incluida la activación o desactivación con `is_active`. Requiere "
            "`expected_version`; si el insumo cambió, 409 `stale_version` con el vigente en "
            "`current`. La unidad no cambia cuando el insumo ya tiene registros (422 "
            "`input_unit_locked`). Para quitar la presentación se envían `package_type` y "
            "`package_size` en `null`."
        ),
        request=AgriculturalInputUpdateSerializer,
        responses={
            200: AgriculturalInputSerializer,
            409: AgriculturalInputConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina un insumo creado por error. Requiere `expected_version` en la URL. Si algún "
            "registro lo usa, 409 `input_has_records` (se desactiva en su lugar). El historial "
            "del insumo se conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` del insumo que se leyó.",
            )
        ],
        responses={
            204: None,
            409: AgriculturalInputConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class AgriculturalInputViewSet(GenericViewSet):
    serializer_class = AgriculturalInputSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "inputs.view_agriculturalinput",
        "retrieve": "inputs.view_agriculturalinput",
        "create": "inputs.add_agriculturalinput",
        "partial_update": "inputs.change_agriculturalinput",
        "destroy": "inputs.delete_agriculturalinput",
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = AgriculturalInputListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        inputs = list_inputs(request.user, producer=query.validated_data.get("producer"))
        return Response({"results": AgriculturalInputSerializer(inputs, many=True).data})

    def retrieve(self, request, pk):
        return Response(AgriculturalInputSerializer(get_input(request.user, pk)).data)

    def create(self, request):
        serializer = AgriculturalInputCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = create_input(request.user, serializer.to_model_data())
        return Response(
            AgriculturalInputSerializer(item).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("agricultural-input-detail", args=[item.pk])},
        )

    def partial_update(self, request, pk):
        serializer = AgriculturalInputUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_model_data()
        expected_version = data.pop("expected_version")
        item = update_input(request.user, pk, expected_version, data)
        return Response(AgriculturalInputSerializer(item).data)

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP.
        serializer = AgriculturalInputDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_input(request.user, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        if isinstance(exc, StaleInputVersion):
            exc.extra = {"current": AgriculturalInputSerializer(exc.current_input).data}
        return super().handle_exception(exc)
