from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleDryingLogVersion
from .log_serializers import (
    DryingHoursErrorSerializer,
    DryingLogConflictErrorSerializer,
    DryingLogCreateSerializer,
    DryingLogDeleteSerializer,
    DryingLogUpdateSerializer,
)
from .serializers import DryingLogSerializer
from .services.logs import delete_log, record_log, update_log


@extend_schema_view(
    create=extend_schema(
        description=(
            "Registra la bitácora de un día de un secado en curso; llega desde la cola del "
            "dispositivo. El `id` lo genera el cliente: reenviar la misma con los mismos datos "
            "responde 200 con la que ya existe, y con otros datos 409 `drying_log_id_conflict`. "
            "Una por fecha (la local de `measured_at`): otra el mismo día es 409 "
            "`duplicate_drying_log_date` con la existente en `existing`. El día de secado se "
            "cuenta desde la fecha de inicio. Las horas al sol y a la sombra no pasan de las que "
            "ese día estuvo en secado (400 en `fields.sun_hours`, con `available_hours`)."
        ),
        request=DryingLogCreateSerializer,
        responses={
            201: DryingLogSerializer,
            200: DryingLogSerializer,
            400: DryingHoursErrorSerializer,
            409: DryingLogConflictErrorSerializer,
            **error_responses(401, 403, 404),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Corrige una bitácora mientras el secado sigue en curso; cambiar la hora de la "
            "medición puede cambiar su fecha y su día. Requiere `expected_version`; si cambió, "
            "409 `stale_version` con la vigente en `current`. Con el secado terminado, 409 "
            "`drying_not_in_progress`."
        ),
        request=DryingLogUpdateSerializer,
        responses={
            200: DryingLogSerializer,
            400: DryingHoursErrorSerializer,
            409: DryingLogConflictErrorSerializer,
            **error_responses(401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina una bitácora registrada por error mientras el secado sigue en curso. "
            "Requiere `expected_version` en la URL."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` de la bitácora que se leyó.",
            )
        ],
        responses={
            204: None,
            409: DryingLogConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class DryingLogViewSet(GenericViewSet):
    serializer_class = DryingLogSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "create": "drying.log_drying",
        "partial_update": "drying.log_drying",
        "destroy": "drying.log_drying",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def create(self, request, lot_id):
        serializer = DryingLogCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry, created = record_log(request.user, lot_id, serializer.validated_data)
        return Response(
            DryingLogSerializer(entry).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def partial_update(self, request, lot_id, pk):
        serializer = DryingLogUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        entry = update_log(request.user, lot_id, pk, expected_version, data)
        return Response(DryingLogSerializer(entry).data)

    def destroy(self, request, lot_id, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP.
        serializer = DryingLogDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_log(request.user, lot_id, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        if isinstance(exc, StaleDryingLogVersion):
            exc.extra = {"current": DryingLogSerializer(exc.current_entry).data}
        return super().handle_exception(exc)
