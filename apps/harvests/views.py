from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleHarvestVersion
from .serializers import (
    CollectorListSerializer,
    CollectorQuerySerializer,
    HarvestConflictErrorSerializer,
    HarvestCreateSerializer,
    HarvestDeleteQuerySerializer,
    HarvestListQuerySerializer,
    HarvestListSerializer,
    HarvestSerializer,
    HarvestUpdateSerializer,
)
from .services.create import create_harvest
from .services.delete import delete_harvest
from .services.queries import collector_options, get_harvest, list_harvests
from .services.update import update_harvest


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las cosechas recogidas en el periodo, `from` y `to` incluidos, de hasta 92 días, de "
            "la más reciente a la más antigua. Sin paginar: los filtros de variedad, recolector y "
            "lote, y los totales, los aplica el dispositivo, para que funcionen igual sin "
            "conexión. `farm` y `plot` acotan al detalle de una finca o de una parcela."
        ),
        parameters=[
            OpenApiParameter("from", str, required=True, description="Fecha inicial (incluida)."),
            OpenApiParameter("to", str, required=True, description="Fecha final (incluida)."),
            OpenApiParameter("farm", str, description="Solo las cosechas de esta finca."),
            OpenApiParameter("plot", str, description="Solo las cosechas de esta parcela."),
            OpenApiParameter("producer", str, description="Solo para la cuenta técnica."),
        ],
        responses={200: HarvestListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        responses={200: HarvestSerializer, **error_responses(401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Registra una cosecha en una parcela con ficha y siembras. `id` lo genera el "
            "dispositivo: reenviar el mismo `id` con los mismos datos responde 200 con la "
            "cosecha ya creada; con otros datos, 409 `harvest_id_conflict`. La parcela sin "
            "siembras es 422 `plot_not_characterized`; una variedad que no está en la ficha, 422 "
            "`variety_not_in_plot`; un recolector que no cumple, 422 `collector_not_available`. "
            "Una parcela o finca inactivas no impiden registrar."
        ),
        request=HarvestCreateSerializer,
        responses={
            200: HarvestSerializer,
            201: HarvestSerializer,
            409: HarvestConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Corrige la fecha, el peso, la variedad o el recolector de una cosecha que no forma "
            "un lote; la parcela no cambia. Requiere `expected_version`. La variedad y el "
            "recolector se validan solo si cambian. 409 `stale_version` trae la cosecha vigente "
            "en `current`; una cosecha en un lote responde 409 `harvest_in_lot`."
        ),
        request=HarvestUpdateSerializer,
        responses={
            200: HarvestSerializer,
            409: HarvestConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina una cosecha registrada por error. Requiere `expected_version` en la URL. "
            "Una cosecha en un lote no se elimina (409 `harvest_in_lot`). El historial se "
            "conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` de la cosecha que se leyó.",
            )
        ],
        responses={
            204: None,
            409: HarvestConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class HarvestViewSet(GenericViewSet):
    serializer_class = HarvestSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "harvests.view_harvest",
        "retrieve": "harvests.view_harvest",
        "create": "harvests.add_harvest",
        "partial_update": "harvests.change_harvest",
        "destroy": "harvests.delete_harvest",
        "collectors": "harvests.view_harvest",
    }
    filter_backends = []
    # La lista devuelve todo el periodo de una vez (ver su descripción): sin esto, el esquema
    # heredaba la paginación por defecto y anunciaba `page` y `page_size`, que no hacen nada.
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = HarvestListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        period = query.validated_data
        harvests = list_harvests(
            request.user,
            period["from"],
            period["to"],
            farm_id=period.get("farm"),
            plot_id=period.get("plot"),
            producer_id=period.get("producer"),
        )
        return Response({"results": HarvestSerializer(harvests, many=True).data})

    def retrieve(self, request, pk):
        return Response(HarvestSerializer(get_harvest(request.user, pk)).data)

    def create(self, request):
        serializer = HarvestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        harvest, created = create_harvest(request.user, serializer.validated_data)
        data = HarvestSerializer(harvest).data
        if not created:
            return Response(data)
        return Response(
            data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("harvest-detail", args=[harvest.pk])},
        )

    def partial_update(self, request, pk):
        serializer = HarvestUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        harvest = update_harvest(request.user, pk, expected_version, data)
        return Response(HarvestSerializer(harvest).data)

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP y
        # algunos intermediarios lo descartan.
        query = HarvestDeleteQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        delete_harvest(request.user, pk, query.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description=(
            "Las cuentas del productor que pueden ser recolectoras, activas e inactivas, con las "
            "fincas en las que trabajan y si quien pregunta puede nombrarlas. La cuenta técnica "
            "envía `producer`."
        ),
        parameters=[OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")],
        responses={200: CollectorListSerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"])
    def collectors(self, request):
        query = CollectorQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        options = collector_options(request.user, query.validated_data.get("producer"))
        return Response({"results": CollectorListSerializer({"results": options}).data["results"]})

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con la cosecha del dominio; aquí se convierte en lo que el
        # formulario necesita para cargar los valores vigentes sin otra consulta.
        if isinstance(exc, StaleHarvestVersion):
            exc.extra = {"current": HarvestSerializer(exc.current_harvest).data}
        return super().handle_exception(exc)
