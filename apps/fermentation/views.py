from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import (
    FermentationListQuerySerializer,
    FermentationListSerializer,
    FermentationProcessSerializer,
    StartOptionsQuerySerializer,
    StartOptionsSerializer,
)
from .services.queries import get_fermentation, list_fermentations, start_options


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
)
class FermentationViewSet(GenericViewSet):
    serializer_class = FermentationProcessSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "fermentation.log_turns",
        # Una fermentación se ve en la ficha de su lote: la ve quien ve el lote.
        "retrieve": "lots.view_lot",
        "start_options": "fermentation.manage_fermentation",
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
