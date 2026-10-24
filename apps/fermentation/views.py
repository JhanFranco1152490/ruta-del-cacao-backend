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

from .exceptions import StaleFermentationVersion
from .serializers import (
    CapacityErrorSerializer,
    FermentationConflictErrorSerializer,
    FermentationFinishSerializer,
    FermentationListQuerySerializer,
    FermentationListSerializer,
    FermentationProcessSerializer,
    FermentationStartSerializer,
    FermentationStartUpdateSerializer,
    StartOptionsQuerySerializer,
    StartOptionsSerializer,
)
from .services.finish import finish_fermentation
from .services.queries import get_fermentation, list_fermentations, start_options
from .services.start import start_fermentation
from .services.update import correct_start


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las fermentaciones en curso de las fincas que alcanza la sesión, con sus volteos, "
            "sin paginar: el dispositivo las guarda todas para trabajar sin conexión. De la más "
            "antigua a la más reciente."
        ),
        parameters=[
            OpenApiParameter("farm", OpenApiTypes.UUID, description="Solo las de esta finca."),
            OpenApiParameter(
                "producer",
                OpenApiTypes.UUID,
                description="Solo la cuenta técnica: el productor cuyas fermentaciones se ve.",
            ),
        ],
        responses={200: FermentationListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        description="La fermentación de un lote, en curso o terminada. Se busca por el lote.",
        responses={200: FermentationProcessSerializer, **error_responses(401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Inicia la fermentación de un lote Generado en un cajón libre de su finca: el lote "
            "pasa a En fermentación y el cajón a Ocupado, en una sola transacción. Si el lote "
            "pesa más que la capacidad del cajón, 422 `lot_exceeds_capacity` con `capacity_kg` y "
            "`green_weight_kg`, salvo con `confirm_over_capacity`. El inicio no puede ser futuro "
            "ni anterior al día de la cosecha."
        ),
        request=FermentationStartSerializer,
        responses={
            201: FermentationProcessSerializer,
            409: FermentationConflictErrorSerializer,
            422: CapacityErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Corrige el inicio de una fermentación sin volteos: el cajón, la hora y el "
            "responsable. Cambiar de cajón libera el anterior y ocupa el nuevo. Requiere "
            "`expected_version`; si cambió, 409 `stale_version` con la vigente en `current`. Con "
            "volteos, 409 `fermentation_has_turns`."
        ),
        request=FermentationStartUpdateSerializer,
        responses={
            200: FermentationProcessSerializer,
            409: FermentationConflictErrorSerializer,
            422: CapacityErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class FermentationViewSet(GenericViewSet):
    serializer_class = FermentationProcessSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "fermentation.log_turns",
        # Una fermentación se ve en la ficha de su lote: la ve quien ve el lote.
        "retrieve": "lots.view_lot",
        "start_options": "fermentation.manage_fermentation",
        "create": "fermentation.manage_fermentation",
        "partial_update": "fermentation.manage_fermentation",
        "finish": "fermentation.manage_fermentation",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = FermentationListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        processes = list_fermentations(
            request.user,
            farm=query.validated_data.get("farm"),
            producer=query.validated_data.get("producer"),
        )
        return Response({"results": FermentationProcessSerializer(processes, many=True).data})

    def retrieve(self, request, pk):
        return Response(FermentationProcessSerializer(get_fermentation(request.user, pk)).data)

    def create(self, request):
        serializer = FermentationStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        process = start_fermentation(request.user, serializer.validated_data)
        return Response(
            FermentationProcessSerializer(get_fermentation(request.user, process.pk)).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("fermentation-detail", args=[process.pk])},
        )

    def partial_update(self, request, pk):
        serializer = FermentationStartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        process = correct_start(request.user, pk, expected_version, data)
        return Response(
            FermentationProcessSerializer(get_fermentation(request.user, process.pk)).data
        )

    @extend_schema(
        description=(
            "Finaliza una fermentación en curso: el lote pasa a Fermentado y el cajón queda "
            "Disponible, en una sola transacción. Necesita al menos un volteo (409 "
            "`fermentation_without_turns`); el fin no puede ser anterior al último volteo ni "
            "futuro. Requiere `expected_version`; si cambió, 409 `stale_version` con la vigente "
            "en `current`."
        ),
        request=FermentationFinishSerializer,
        responses={
            200: FermentationProcessSerializer,
            409: FermentationConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    )
    @action(detail=True, methods=["post"])
    def finish(self, request, pk):
        serializer = FermentationFinishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        process = finish_fermentation(request.user, pk, expected_version, data)
        return Response(
            FermentationProcessSerializer(get_fermentation(request.user, process.pk)).data
        )

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con el lote; aquí se arma lo que el formulario necesita
        # para cargar los valores vigentes sin otra consulta.
        if isinstance(exc, StaleFermentationVersion):
            current = get_fermentation(self.request.user, exc.lot_id)
            exc.extra = {"current": FermentationProcessSerializer(current).data}
        return super().handle_exception(exc)

    @extend_schema(
        description=(
            "Lo que necesita el formulario de iniciar la fermentación de un lote Generado, o de "
            "corregir el inicio de una sin volteos: los cajones libres de la finca del lote (al "
            "corregir, también el que ya ocupa), quién puede ser responsable, el peso del lote y "
            "desde cuándo puede empezar (el día de su cosecha). Si el lote está en otro estado, "
            "409 `lot_invalid_status` con `current_status`."
        ),
        parameters=[StartOptionsQuerySerializer],
        responses={200: StartOptionsSerializer, **error_responses(400, 401, 403, 404, 409)},
    )
    @action(detail=False, methods=["get"], url_path="start-options")
    def start_options(self, request):
        query = StartOptionsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        options = start_options(request.user, query.validated_data["lot"])
        return Response(StartOptionsSerializer(options).data)
