from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleParameters
from .serializers import (
    PostharvestParametersSaveSerializer,
    PostharvestParametersSerializer,
    ProducerQuerySerializer,
)
from .services.queries import get_parameters
from .services.save import save_parameters

PRODUCER_PARAMETER = OpenApiParameter(
    "producer",
    OpenApiTypes.UUID,
    description="Solo la cuenta técnica, y para ella obligatorio: el productor cuyos parámetros "
    "se quiere ver.",
)


def errors_by_parameter(errors: dict) -> dict:
    """Sube los errores de cada parámetro al primer nivel (`fields.entry_moisture_min_pct`): el
    formato común de errores junta lo anidado en una lista y perdería a qué campo corresponde
    cada mensaje. Los nombres de los parámetros no chocan con los del cuerpo."""
    flat = {name: messages for name, messages in errors.items() if name != "values"}
    values = errors.get("values")
    if isinstance(values, dict):
        flat.update(values)
    elif values is not None:
        flat["values"] = values
    return flat


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
    update=extend_schema(
        description=(
            "Guarda los quince valores juntos. Requiere `expected_version` (0 si el productor "
            "usa la línea base); si cambiaron entretanto, 409 `stale_version` con los vigentes en "
            "`current`. Cada error va en `fields.{campo}`; el de un mínimo mayor que su "
            "máximo, en el mínimo. La cuenta técnica nombra el productor en `producer`."
        ),
        request=PostharvestParametersSaveSerializer,
        responses={
            200: PostharvestParametersSerializer,
            **error_responses(400, 401, 403, 404, 409),
        },
    ),
)
class PostharvestParametersViewSet(ViewSet):
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "retrieve": "postharvest_parameters.view_postharvestparameters",
        "update": "postharvest_parameters.change_postharvestparameters",
    }

    def retrieve(self, request):
        query = ProducerQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        state = get_parameters(request.user, query.validated_data.get("producer"))
        return Response(PostharvestParametersSerializer(state).data)

    def update(self, request):
        serializer = PostharvestParametersSaveSerializer(data=request.data)
        if not serializer.is_valid():
            raise ValidationError(errors_by_parameter(serializer.errors))
        data = serializer.validated_data
        state = save_parameters(
            request.user, data.get("producer"), data["expected_version"], dict(data["values"])
        )
        return Response(PostharvestParametersSerializer(state).data)

    def handle_exception(self, exc):
        if isinstance(exc, StaleParameters):
            exc.extra = {"current": PostharvestParametersSerializer(exc.current_state).data}
        return super().handle_exception(exc)
