from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import AreaMismatch, PlotIdConflict, PlotOverlap, StalePlotVersion
from .pagination import PlotPagination
from .serializers import (
    OverlapSerializer,
    PlotConflictErrorSerializer,
    PlotCreateSerializer,
    PlotDeleteQuerySerializer,
    PlotListQuerySerializer,
    PlotRuleErrorSerializer,
    PlotSerializer,
    PlotUpdateSerializer,
    VertexSerializer,
)
from .services import (
    count_characterizations,
    create_plot,
    delete_plot,
    get_plot,
    list_plots,
    update_plot,
    with_characterization,
)
from .services.queries import CHARACTERIZATION_FILTERS, PLOT_ORDERINGS


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("farm", str, description="Solo las parcelas de esta finca."),
            OpenApiParameter(
                "producer", str, description="Solo las parcelas de las fincas de este productor."
            ),
            OpenApiParameter(
                "characterization",
                str,
                enum=list(CHARACTERIZATION_FILTERS),
                description=(
                    "Solo las parcelas con ficha (`done`) o sin ella (`pending`). No cambia "
                    "`characterization_counts`, que cuenta con los demás filtros."
                ),
            ),
            OpenApiParameter("is_active", bool, description="Solo activas o solo inactivas."),
            OpenApiParameter(
                "ordering",
                str,
                enum=list(PLOT_ORDERINGS),
                description=(
                    "`code` (por defecto) o `producer,farm,code`: por nombre del productor, "
                    "nombre de la finca y código, para agrupar. Cada nivel desempata por su id."
                ),
            ),
            OpenApiParameter("search", str, description="Busca en el código, sin tildes."),
        ],
        # 400: un filtro mal formado. 404: página fuera de rango.
        responses={200: PlotSerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
    retrieve=extend_schema(responses={200: PlotSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Registra una parcela en una finca del productor de la sesión. `id` es opcional: el "
            "dispositivo lo genera al registrar sin conexión. Reenviar el mismo `id` con el "
            "mismo contenido responde 200 con la parcela ya creada; con otro contenido, 409 "
            "`plot_id_conflict`, con la parcela del servidor en `current` si es del mismo "
            "productor. El 422 de `area_mismatch` trae `measured_area_hectares`, y el de "
            "`plot_overlap`, las parcelas invadidas y el contorno sugerido."
        ),
        request=PlotCreateSerializer,
        responses={
            200: PlotSerializer,
            201: PlotSerializer,
            409: PlotConflictErrorSerializer,
            422: PlotRuleErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edición parcial, incluida la activación o desactivación con `is_active`. "
            "`boundary` reemplaza el contorno completo y `null` lo quita. Requiere "
            "`expected_version`; si la parcela cambió responde 409 `stale_version` con la "
            "versión del servidor en `current`."
        ),
        request=PlotUpdateSerializer,
        responses={
            200: PlotSerializer,
            409: PlotConflictErrorSerializer,
            422: PlotRuleErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina una parcela creada por error. Requiere `expected_version` en la URL. Si algo "
            "depende de la parcela responde 409 `plot_has_records` (se desactiva en su lugar); "
            "si cambió, 409 `stale_version` con la versión del servidor en `current`. Con la "
            "finca inactiva, 422 `farm_inactive`. El historial de la parcela se conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` de la parcela que se leyó.",
            )
        ],
        responses={
            204: None,
            409: PlotConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
)
class PlotViewSet(GenericViewSet):
    serializer_class = PlotSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "plots.view_plot",
        "retrieve": "plots.view_plot",
        "create": "plots.add_plot",
        "partial_update": "plots.change_plot",
        "destroy": "plots.delete_plot",
    }
    # Los filtros los resuelve el servicio, con el alcance del productor de la sesión.
    filter_backends = []
    pagination_class = PlotPagination
    lookup_value_converter = "uuid"

    def list(self, request):
        # Se pasa un dict y no el QueryDict: con un QueryDict, DRF toma un booleano ausente
        # como `false` y filtraría las activas sin que nadie lo pidiera.
        query = PlotListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        plots = list_plots(
            request.user,
            farm_id=filters.get("farm"),
            producer_id=filters.get("producer"),
            is_active=filters.get("is_active"),
            search=filters.get("search"),
            ordering=filters.get("ordering", "code"),
        )
        # Los conteos van antes del filtro de caracterización: dicen cuántas de todas las que
        # calzan con los demás filtros tienen ficha.
        counts = count_characterizations(plots)
        page = self.paginate_queryset(
            with_characterization(plots, filters.get("characterization"))
        )
        return self.paginator.get_paginated_response(
            PlotSerializer(page, many=True).data, characterization_counts=counts
        )

    def retrieve(self, request, pk):
        return Response(PlotSerializer(get_plot(request.user, pk)).data)

    def create(self, request):
        serializer = PlotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        plot, created = create_plot(request.user, serializer.validated_data)
        if not created:
            return Response(PlotSerializer(plot).data)
        return Response(
            PlotSerializer(plot).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("plot-detail", args=[plot.pk])},
        )

    def partial_update(self, request, pk):
        serializer = PlotUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        return Response(PlotSerializer(update_plot(request.user, pk, expected_version, data)).data)

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP,
        # algunos intermediarios lo descartan y el esquema OpenAPI no lo documenta.
        query = PlotDeleteQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        delete_plot(request.user, pk, query.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        # Los servicios lanzan los errores con objetos del dominio; aquí se convierten en los
        # datos que la interfaz necesita para ofrecer la corrección sin otra consulta.
        if isinstance(exc, (StalePlotVersion, PlotIdConflict)) and exc.current_plot is not None:
            exc.extra = {"current": PlotSerializer(exc.current_plot).data}
        elif isinstance(exc, AreaMismatch):
            exc.extra = {"measured_area_hectares": str(exc.measured_area_hectares)}
        elif isinstance(exc, PlotOverlap):
            exc.extra = _overlap_extra(exc)
        elif isinstance(exc, DjangoValidationError) and hasattr(exc, "error_dict"):
            exc = ValidationError(exc.message_dict)
        return super().handle_exception(exc)


def _overlap_extra(exc: PlotOverlap) -> dict:
    overlaps = [
        {
            "plot_id": plot.pk,
            "code": plot.code,
            "overlap_area_hectares": area,
            "boundary": plot.boundary,
        }
        for plot, area in exc.overlaps
    ]
    suggestion = exc.suggested_boundary
    measured = exc.suggested_measured_area_hectares
    return {
        "overlaps": OverlapSerializer(overlaps, many=True).data,
        "suggested_boundary": (
            None if suggestion is None else VertexSerializer(suggestion, many=True).data
        ),
        "suggested_measured_area_hectares": None if measured is None else str(measured),
    }
