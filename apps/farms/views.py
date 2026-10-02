from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.exceptions import ApiError
from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import FarmIdConflict, StaleFarmVersion
from .filters import FarmFilterSerializer, FarmMapPointsFilterSerializer, validated_filters
from .serializers import (
    MODEL_TO_API_FIELDS,
    FarmConflictErrorSerializer,
    FarmCreateSerializer,
    FarmMapPointSerializer,
    FarmMunicipalityCountSerializer,
    FarmSerializer,
    FarmUpdateSerializer,
)
from .services import (
    create_farm,
    get_farm,
    list_farms,
    municipality_counts,
    municipality_points,
    update_farm,
)

# Los mismos filtros en el listado y en el mapa: así los dos muestran siempre lo mismo.
FARM_FILTER_PARAMETERS = [
    OpenApiParameter(
        "search", str, description="Busca en nombre, municipio o detalles, sin distinguir tildes."
    ),
    OpenApiParameter("producer", OpenApiTypes.UUID, description="Solo las de este productor."),
    OpenApiParameter("municipality", str, description="Código DIVIPOLA del municipio."),
]


@extend_schema_view(
    list=extend_schema(
        parameters=FARM_FILTER_PARAMETERS,
        # 400: filtro mal formado. 404: página fuera de rango.
        responses={200: FarmSerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
    retrieve=extend_schema(responses={200: FarmSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Crea una finca del productor de la sesión o, para la asociación, del que indica "
            "`producer_id` (obligatorio en ese caso; 403 si ese productor no encendió el acceso "
            "de la asociación). `id` es opcional: el dispositivo lo "
            "genera al registrar sin conexión. Reenviar el mismo `id` con el mismo contenido "
            "responde 200 con la finca ya creada; con otro contenido, 409 `farm_id_conflict`. "
            "Si la finca es del mismo productor, el 409 trae la del servidor en `current`, para "
            "enviar el cambio como un PATCH con su `version`; si es de otro productor, no."
        ),
        request=FarmCreateSerializer,
        responses={
            200: FarmSerializer,
            201: FarmSerializer,
            409: FarmConflictErrorSerializer,
            **error_responses(400, 401, 403, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edición parcial, incluida la activación o desactivación con `is_active`. La "
            "asociación solo edita fincas de productores con el acceso encendido (si no, 403). "
            "Requiere "
            "`expected_version`; si la finca cambió responde 409 `stale_version` con la versión "
            "del servidor en `current`."
        ),
        request=FarmUpdateSerializer,
        responses={
            200: FarmSerializer,
            409: FarmConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
)
class FarmViewSet(GenericViewSet):
    serializer_class = FarmSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "farms.view_farm",
        "retrieve": "farms.view_farm",
        "create": "farms.add_farm",
        "partial_update": "farms.change_farm",
        "map_municipalities": "farms.view_farm",
        "map_points": "farms.view_farm",
    }
    # La búsqueda la resuelve el servicio: el municipio se busca por su nombre en el catálogo.
    filter_backends = []
    lookup_value_converter = "uuid"

    def get_queryset(self):
        return list_farms(
            self.request.user,
            **validated_filters(FarmFilterSerializer, self.request.query_params),
        )

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response(FarmSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(FarmSerializer(get_farm(request.user, pk)).data)

    def create(self, request):
        serializer = FarmCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        farm, created = create_farm(request.user, serializer.to_model_data())
        if not created:
            return Response(FarmSerializer(farm).data)
        return Response(
            FarmSerializer(farm).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("farm-detail", args=[farm.pk])},
        )

    def partial_update(self, request, pk):
        serializer = FarmUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_model_data()
        expected_version = data.pop("expected_version")
        return Response(FarmSerializer(update_farm(request.user, pk, expected_version, data)).data)

    @extend_schema(
        description="Cuántas fincas hay en cada municipio, con el alcance y filtros del listado.",
        parameters=FARM_FILTER_PARAMETERS,
        responses={
            200: FarmMunicipalityCountSerializer(many=True),
            **error_responses(400, 401, 403),
        },
    )
    @action(detail=False, methods=["get"], url_path="map/municipalities")
    def map_municipalities(self, request):
        filters = validated_filters(FarmFilterSerializer, request.query_params)
        counts = municipality_counts(request.user, **filters)
        return Response(FarmMunicipalityCountSerializer(counts, many=True).data)

    @extend_schema(
        description=(
            "Las fincas de un municipio (`municipality`, obligatorio) con lo justo para "
            "dibujarlas, sin paginar, con el alcance y filtros del listado."
        ),
        parameters=FARM_FILTER_PARAMETERS,
        responses={200: FarmMapPointSerializer(many=True), **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], url_path="map/points")
    def map_points(self, request):
        filters = validated_filters(FarmMapPointsFilterSerializer, request.query_params)
        points = municipality_points(request.user, **filters)
        return Response(FarmMapPointSerializer(points, many=True).data)

    def handle_exception(self, exc):
        if isinstance(exc, (StaleFarmVersion, FarmIdConflict)) and exc.current_farm is not None:
            exc.extra = {"current": FarmSerializer(exc.current_farm).data}
        # Los servicios hablan con los nombres del modelo; el cliente debe ver los de la API.
        if isinstance(exc, DjangoValidationError) and hasattr(exc, "error_dict"):
            exc = ValidationError(_api_field_names(exc.message_dict))
        elif isinstance(exc, ApiError) and exc.fields:
            exc.fields = _api_field_names(exc.fields)
        return super().handle_exception(exc)


def _api_field_names(errors: dict) -> dict:
    return {MODEL_TO_API_FIELDS.get(name, name): messages for name, messages in errors.items()}
