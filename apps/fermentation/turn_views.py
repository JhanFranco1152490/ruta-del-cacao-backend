from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses
from apps.common.serializers import DeviationSerializer

from .alerts import turn_deviations
from .exceptions import StaleTurnVersion
from .serializers import (
    FermentationTurnCreateSerializer,
    FermentationTurnDeleteSerializer,
    FermentationTurnSavedSerializer,
    FermentationTurnSerializer,
    FermentationTurnUpdateSerializer,
    TurnConflictErrorSerializer,
    turn_row,
)
from .services.turns import delete_turn, record_turn, turn_number, update_turn


def represent(turn) -> dict:
    return FermentationTurnSerializer(
        turn_row(turn, turn_number(turn), turn.process.started_at)
    ).data


def saved(turn) -> dict:
    """El volteo guardado con sus desvíos. Un reenvío desde la cola también los dice: el teléfono
    los muestra la primera vez que el volteo llega."""
    deviations = DeviationSerializer(turn_deviations(turn), many=True).data
    return {**represent(turn), "alerts": deviations}


@extend_schema_view(
    create=extend_schema(
        description=(
            "Registra un volteo de una fermentación en curso; llega desde la cola del "
            "dispositivo. El `id` lo genera el cliente: reenviar el mismo con los mismos datos "
            "responde 200 con el que ya existe, y con otros datos 409 `turn_id_conflict`. La "
            "hora se guarda sin segundos, y dos volteos de la misma fermentación en el mismo "
            "minuto son el mismo: 409 `duplicate_turn_time` con el existente en `existing`. El "
            "número es su posición por hora. `alerts` trae los desvíos de temperatura y de pH "
            "del grano (también en un reenvío); un desvío nunca impide guardarlo."
        ),
        request=FermentationTurnCreateSerializer,
        responses={
            201: FermentationTurnSavedSerializer,
            200: FermentationTurnSavedSerializer,
            409: TurnConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Corrige un volteo mientras la fermentación sigue en curso. Requiere "
            "`expected_version`; si cambió, 409 `stale_version` con el vigente en `current`. Con "
            "la fermentación terminada, 409 `fermentation_not_in_progress`. `alerts` trae los "
            "desvíos que el volteo cumple tras corregirlo; los avisos de los que ya no cumple se "
            "retiran."
        ),
        request=FermentationTurnUpdateSerializer,
        responses={
            200: FermentationTurnSavedSerializer,
            409: TurnConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina un volteo registrado por error mientras la fermentación sigue en curso. "
            "Requiere `expected_version` en la URL. Los siguientes cambian de número."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` del volteo que se leyó.",
            )
        ],
        responses={
            204: None,
            409: TurnConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class FermentationTurnViewSet(GenericViewSet):
    serializer_class = FermentationTurnSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "create": "fermentation.log_turns",
        "partial_update": "fermentation.log_turns",
        "destroy": "fermentation.log_turns",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def create(self, request, lot_id):
        serializer = FermentationTurnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        turn, created = record_turn(request.user, lot_id, serializer.validated_data)
        return Response(
            saved(turn), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )

    def partial_update(self, request, lot_id, pk):
        serializer = FermentationTurnUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        return Response(saved(update_turn(request.user, lot_id, pk, expected_version, data)))

    def destroy(self, request, lot_id, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP.
        serializer = FermentationTurnDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_turn(request.user, lot_id, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        if isinstance(exc, StaleTurnVersion):
            exc.extra = {"current": represent(exc.current_turn)}
        return super().handle_exception(exc)
