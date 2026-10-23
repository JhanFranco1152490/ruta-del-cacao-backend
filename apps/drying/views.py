from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleDryingVersion
from .serializers import (
    DryingConflictErrorSerializer,
    DryingListQuerySerializer,
    DryingListSerializer,
    DryingProcessSerializer,
    DryingStartOptionsQuerySerializer,
    DryingStartOptionsSerializer,
    DryingStartSerializer,
    DryingStartUpdateSerializer,
    EntryMoistureErrorSerializer,
)
from .services.queries import get_drying, list_dryings, start_options
from .services.start import start_drying
from .services.update import correct_start


@extend_schema_view(
    list=extend_schema(
        description=(
            "Los secados en curso de las fincas que alcanza la sesión, con su bitácora, sin "
            "paginar: el dispositivo los guarda todos para trabajar sin conexión, y con ellos "
            "arma también la ficha de un lote en secado. Del más antiguo al más reciente."
        ),
        parameters=[
            OpenApiParameter("farm", OpenApiTypes.UUID, description="Solo los de esta finca."),
            OpenApiParameter(
                "producer",
                OpenApiTypes.UUID,
                description="Solo la cuenta técnica: el productor cuyos secados se ve.",
            ),
        ],
        responses={200: DryingListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        description="El secado de un lote, en curso o terminado. Se busca por el lote.",
        responses={200: DryingProcessSerializer, **error_responses(401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Inicia el secado de un lote Fermentado en una marquesina libre de su finca: el lote "
            "pasa a En secado y la marquesina a Ocupada, en una sola transacción. Si la humedad "
            "de entrada sale del rango que espera el productor, 422 "
            "`entry_moisture_out_of_range` con `range`, salvo con `confirm_entry_moisture`. El "
            "inicio no puede ser futuro ni anterior al fin de la fermentación."
        ),
        request=DryingStartSerializer,
        responses={
            201: DryingProcessSerializer,
            409: DryingConflictErrorSerializer,
            422: EntryMoistureErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Corrige el inicio de un secado sin bitácora: la marquesina, la hora, la humedad de "
            "entrada y el responsable. Cambiar de marquesina libera la anterior y ocupa la nueva. "
            "Requiere `expected_version`; si cambió, 409 `stale_version` con el vigente en "
            "`current`. Con bitácora, 409 `drying_has_logs`."
        ),
        request=DryingStartUpdateSerializer,
        responses={
            200: DryingProcessSerializer,
            409: DryingConflictErrorSerializer,
            422: EntryMoistureErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class DryingViewSet(GenericViewSet):
    serializer_class = DryingProcessSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "drying.log_drying",
        # Un secado se ve en la ficha de su lote: lo ve quien ve el lote.
        "retrieve": "lots.view_lot",
        "start_options": "drying.manage_drying",
        "create": "drying.manage_drying",
        "partial_update": "drying.manage_drying",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = DryingListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        processes = list_dryings(
            request.user,
            farm=query.validated_data.get("farm"),
            producer=query.validated_data.get("producer"),
        )
        return Response({"results": DryingProcessSerializer(processes, many=True).data})

    def retrieve(self, request, pk):
        return Response(DryingProcessSerializer(get_drying(request.user, pk)).data)

    def create(self, request):
        serializer = DryingStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        process = start_drying(request.user, serializer.validated_data)
        return Response(
            DryingProcessSerializer(get_drying(request.user, process.pk)).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("drying-detail", args=[process.pk])},
        )

    def partial_update(self, request, pk):
        serializer = DryingStartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        process = correct_start(request.user, pk, expected_version, data)
        return Response(DryingProcessSerializer(get_drying(request.user, process.pk)).data)

    @extend_schema(
        description=(
            "Lo que necesita el formulario de iniciar el secado de un lote Fermentado, o de "
            "corregir el inicio de uno sin bitácora: las marquesinas libres de la finca del lote "
            "(al corregir, también la que ya ocupa), quién puede ser responsable, el rango "
            "esperado de la humedad de entrada y desde cuándo puede empezar (el fin de la "
            "fermentación). Si el lote está en otro estado, 409 `lot_invalid_status` con "
            "`current_status`."
        ),
        parameters=[DryingStartOptionsQuerySerializer],
        responses={200: DryingStartOptionsSerializer, **error_responses(400, 401, 403, 404, 409)},
    )
    @action(detail=False, methods=["get"], url_path="start-options")
    def start_options(self, request):
        query = DryingStartOptionsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options = start_options(request.user, query.validated_data["lot"])
        return Response(DryingStartOptionsSerializer(options).data)

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con el lote; aquí se arma lo que el formulario necesita
        # para cargar los valores vigentes sin otra consulta.
        if isinstance(exc, StaleDryingVersion):
            current = get_drying(self.request.user, exc.lot_id)
            exc.extra = {"current": DryingProcessSerializer(current).data}
        return super().handle_exception(exc)
