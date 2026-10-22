from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import PostharvestParametersSerializer, ProducerQuerySerializer
from .services.queries import get_parameters

PRODUCER_PARAMETER = OpenApiParameter(
    "producer",
    OpenApiTypes.UUID,
    description="Solo la cuenta técnica, y para ella obligatorio: el productor cuyos parámetros "
    "se quiere ver.",
)


@extend_schema_view(
    retrieve=extend_schema(
        description=(
            "Los parámetros de secado vigentes del productor de la sesión, con la línea base al "
            "lado. Si nunca los cambió, `is_default` es verdadero, `values` es la línea base y "
            "`version` es 0."
        ),
        parameters=[PRODUCER_PARAMETER],
        responses={200: PostharvestParametersSerializer, **error_responses(400, 401, 403, 404)},
    ),
)
class PostharvestParametersViewSet(ViewSet):
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "retrieve": "postharvest_parameters.view_postharvestparameters",
    }

    def retrieve(self, request):
        query = ProducerQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        state = get_parameters(request.user, query.validated_data.get("producer"))
        return Response(PostharvestParametersSerializer(state).data)
