from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import DryingListQuerySerializer, DryingListSerializer, DryingProcessSerializer
from .services.queries import get_drying, list_dryings


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
)
class DryingViewSet(GenericViewSet):
    serializer_class = DryingProcessSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "drying.log_drying",
        # Un secado se ve en la ficha de su lote: lo ve quien ve el lote.
        "retrieve": "lots.view_lot",
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
