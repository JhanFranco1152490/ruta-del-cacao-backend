from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.contracts.activity_representation import activity_serializer
from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from ..serializers import (
    DetectionControlSerializer,
    MonitoringResultSerializer,
)
from ..services.controls import create_control_from_detection
from ..services.monitoring import record_monitoring


class MonitoringResultView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.complete_agriculturalactivity"

    @extend_schema(
        operation_id="agricultural_activities_monitoring_create",
        description=(
            "Registra el resultado de un monitoreo (unidades evaluadas y, por cada plaga o "
            "enfermedad, las afectadas; o sin presencia) y lo marca realizado. La incidencia la "
            "calcula el servidor. Lo registra el responsable, quien programa labores en la finca "
            "o el Productor (403 si no). El mismo resultado reenviado responde 200 sin cambios; "
            "otro resultado sobre uno ya registrado, 409 `activity_already_done`. Una plaga "
            "inexistente es 400 en `detections`, no 404; una inactiva, 422 "
            "`pest_disease_inactive` con las afectadas en `pest_disease_ids`. Otra actividad "
            "responde 422 `not_a_monitoring`."
        ),
        request=MonitoringResultSerializer,
        responses={
            200: activity_serializer(),
            201: activity_serializer(),
            **error_responses(400, 401, 403, 404, 409, 422),
        },
    )
    def post(self, request, pk):
        serializer = MonitoringResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity, created = record_monitoring(request.user, pk, serializer.validated_data)
        data = activity_serializer()(activity).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class DetectionControlsView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.add_agriculturalactivity"

    @extend_schema(
        operation_id="phytosanitary_detections_controls_create",
        description=(
            "Crea un control desde una detección: programado (`mode: scheduled`, con fecha desde "
            "hoy, responsable y, si se sabe, qué se va a hacer y el insumo previsto, que no "
            "descuenta) o ya realizado (`mode: done`, con fecha no futura ni anterior al "
            "monitoreo, qué se hizo y los insumos, que se descuentan del inventario de la finca). "
            "Programar pide el permiso de programar; registrarlo realizado, además el de "
            "registrar la realización. `id` lo genera el dispositivo: el mismo control reenviado "
            "responde 200; un `id` que ya usa otra actividad es 400 en `fields.id`. Un monitoreo "
            "sin presencia no tiene detecciones a las que pedir un control."
        ),
        request=DetectionControlSerializer,
        responses={
            200: activity_serializer(),
            201: activity_serializer(),
            **error_responses(400, 401, 403, 404, 422),
        },
    )
    def post(self, request, pk):
        serializer = DetectionControlSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity, created = create_control_from_detection(
            request.user, pk, serializer.validated_data
        )
        data = activity_serializer()(activity).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
