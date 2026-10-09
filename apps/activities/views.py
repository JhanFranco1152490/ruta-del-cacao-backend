from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleActivityVersion
from .serializers import (
    ActivityConflictErrorSerializer,
    ActivityCreateSerializer,
    ActivityDeleteQuerySerializer,
    ActivityUpdateSerializer,
    AgriculturalActivitySerializer,
    AssigneeListSerializer,
    AssigneeQuerySerializer,
    CompletionSerializer,
)
from .services.complete import complete_activity
from .services.create import create_activity
from .services.delete import delete_activity
from .services.queries import assignee_options, get_activity
from .services.update import update_activity


@extend_schema_view(
    retrieve=extend_schema(
        responses={200: AgriculturalActivitySerializer, **error_responses(401, 403, 404)}
    ),
    create=extend_schema(
        description=(
            "Programa una actividad en una parcela activa. `id` lo genera el dispositivo: "
            "reenviar el mismo `id` con el mismo contenido responde 200 con la actividad ya "
            "creada. El control fitosanitario no se programa aquí (422 "
            "`activity_type_not_allowed`)."
        ),
        request=ActivityCreateSerializer,
        responses={
            200: AgriculturalActivitySerializer,
            201: AgriculturalActivitySerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edita o reprograma una actividad programada o retrasada; la parcela no cambia. "
            "Requiere `expected_version`. La fecha y el responsable se validan solo si cambian. "
            "409 `stale_version` trae la actividad vigente en `current`; una realizada responde "
            "409 `activity_already_done` y una vencida, 409 `activity_overdue`."
        ),
        request=ActivityUpdateSerializer,
        responses={
            200: AgriculturalActivitySerializer,
            409: ActivityConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina una actividad programada o retrasada creada por error. Requiere "
            "`expected_version` en la URL. Una realizada o una vencida no se eliminan (409). El "
            "historial se conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` de la actividad que se leyó.",
            )
        ],
        responses={
            204: None,
            409: ActivityConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class AgriculturalActivityViewSet(GenericViewSet):
    serializer_class = AgriculturalActivitySerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "retrieve": "activities.view_agriculturalactivity",
        "create": "activities.add_agriculturalactivity",
        "partial_update": "activities.change_agriculturalactivity",
        "destroy": "activities.delete_agriculturalactivity",
        "completion": "activities.complete_agriculturalactivity",
        "assignees": "activities.view_agriculturalactivity",
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def retrieve(self, request, pk):
        return Response(AgriculturalActivitySerializer(get_activity(request.user, pk)).data)

    def create(self, request):
        serializer = ActivityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity, created = create_activity(request.user, serializer.validated_data)
        data = AgriculturalActivitySerializer(activity).data
        if not created:
            return Response(data)
        return Response(
            data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("agricultural-activity-detail", args=[activity.pk])},
        )

    def partial_update(self, request, pk):
        serializer = ActivityUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        activity = update_activity(request.user, pk, expected_version, data)
        return Response(AgriculturalActivitySerializer(activity).data)

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP y
        # algunos intermediarios lo descartan.
        query = ActivityDeleteQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        delete_activity(request.user, pk, query.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description=(
            "Registra la realización. Llega desde la cola del dispositivo: no pide versión, y el "
            "mismo registro reenviado responde 200 sin cambios. Una realizada con otros datos "
            "responde 409 `activity_already_done`; un monitoreo, 422 "
            "`monitoring_requires_result`. `inputs` debe venir vacío hasta que existan los "
            "insumos."
        ),
        request=CompletionSerializer,
        responses={
            200: AgriculturalActivitySerializer,
            **error_responses(400, 401, 403, 404, 409, 422),
        },
    )
    @action(detail=True, methods=["post"], url_path="completion")
    def completion(self, request, pk):
        serializer = CompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity, _ = complete_activity(request.user, pk, serializer.validated_data)
        return Response(AgriculturalActivitySerializer(activity).data)

    @extend_schema(
        description=(
            "Las cuentas del productor a las que se puede asignar una labor, activas e "
            "inactivas, solo con id y nombre. La cuenta técnica envía `producer`."
        ),
        parameters=[OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")],
        responses={200: AssigneeListSerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"])
    def assignees(self, request):
        query = AssigneeQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        options = assignee_options(request.user, query.validated_data.get("producer"))
        return Response({"results": AssigneeListSerializer({"results": options}).data["results"]})

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con la actividad del dominio; aquí se convierte en lo
        # que el formulario necesita para cargar los valores vigentes sin otra consulta.
        if isinstance(exc, StaleActivityVersion):
            exc.extra = {"current": AgriculturalActivitySerializer(exc.current_activity).data}
        return super().handle_exception(exc)
