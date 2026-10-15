from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.common.activity_representation import activity_serializer
from apps.common.permissions import ActionPermission, HasPermission
from apps.common.schema import error_responses

from .serializers import (
    DetectionControlSerializer,
    HistoryQuerySerializer,
    MonitoringResultSerializer,
    PestDiseaseCreateSerializer,
    PestDiseaseListQuerySerializer,
    PestDiseaseListSerializer,
    PestDiseaseSerializer,
    PestDiseaseUpdateSerializer,
    PestSummarySerializer,
)
from .services.catalog import create_pest_disease, list_pests_diseases, update_pest_disease
from .services.controls import create_control_from_detection
from .services.history import pest_summary, plot_history
from .services.monitoring import record_monitoring

MANAGE_PERMISSION = "health.manage_pestdisease"


@extend_schema_view(
    list=extend_schema(
        description=(
            "El catálogo de plagas y enfermedades, ordenado por nombre y sin paginar: el "
            "formulario del monitoreo las necesita todas, también sin conexión. Basta con tener "
            "sesión."
        ),
        parameters=[
            OpenApiParameter("is_active", bool, description="Solo activas o solo inactivas."),
            OpenApiParameter(
                "search",
                str,
                description=(
                    "Busca en el nombre y en el nombre científico, sin mayúsculas, tildes, "
                    "espacios ni guiones."
                ),
            ),
        ],
        responses={200: PestDiseaseListSerializer, **error_responses(400, 401)},
    ),
    create=extend_schema(
        description=(
            "Registra una plaga o enfermedad. Un nombre que ya existe, aunque se escriba distinto "
            "(`Mazorca negra` y `mazorca-negra`), responde 409 `duplicate_pest_disease_name`."
        ),
        request=PestDiseaseCreateSerializer,
        responses={201: PestDiseaseSerializer, **error_responses(400, 401, 403, 409)},
    ),
    partial_update=extend_schema(
        description=(
            "Edita sus datos, o activa y desactiva con `is_active`. Desactivar no cambia los "
            "monitoreos que ya la usan: solo deja de ofrecerse en los nuevos. `scientific_name` "
            "se quita con `null`."
        ),
        request=PestDiseaseUpdateSerializer,
        responses={200: PestDiseaseSerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
)
class PestDiseaseViewSet(GenericViewSet):
    serializer_class = PestDiseaseSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "create": MANAGE_PERMISSION,
        "partial_update": MANAGE_PERMISSION,
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def get_permissions(self):
        # Son datos de referencia sin información personal, que el formulario del monitoreo
        # necesita: consultarlos solo pide sesión, como el catálogo de variedades.
        if self.action == "list":
            return [IsAuthenticated()]
        return super().get_permissions()

    def list(self, request):
        # Se pasa un dict y no el QueryDict: con un QueryDict, DRF toma un booleano ausente
        # como `false` y filtraría las activas sin que nadie lo pidiera.
        query = PestDiseaseListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        pests = list_pests_diseases(
            is_active=query.validated_data.get("is_active"),
            search=query.validated_data.get("search"),
        )
        return Response(PestDiseaseListSerializer({"results": pests}).data)

    def create(self, request):
        serializer = PestDiseaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pest = create_pest_disease(serializer.validated_data)
        return Response(PestDiseaseSerializer(pest).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk):
        serializer = PestDiseaseUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        pest = update_pest_disease(pk, serializer.validated_data)
        return Response(PestDiseaseSerializer(pest).data)


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


class PlotHistoryView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.view_agriculturalactivity"

    @extend_schema(
        operation_id="plots_phytosanitary_history_retrieve",
        description=(
            "Los monitoreos realizados de la parcela, del más reciente al más antiguo, con la "
            "forma de la actividad y su `monitoring`, y un resumen por plaga (y por cada texto de "
            "Otra) con la última incidencia y la anterior del mismo tipo de muestreo. Sin "
            "paginar: una parcela tiene pocos monitoreos al año. `from` y `to` filtran por la "
            "fecha de realización; `pest_disease` u `other=true` dejan solo los monitoreos donde "
            "se detectó, con esa detección. Una parcela de otra finca o de otro productor es 404."
        ),
        parameters=[
            OpenApiParameter("from", str, description="Fecha inicial (incluida)."),
            OpenApiParameter("to", str, description="Fecha final (incluida)."),
            OpenApiParameter("pest_disease", str, description="Una plaga o enfermedad."),
            OpenApiParameter("other", bool, description="Solo las detecciones de Otra."),
        ],
        responses={
            200: inline_serializer(
                "PhytosanitaryHistory",
                fields={
                    "results": activity_serializer()(many=True),
                    "summary": PestSummarySerializer(many=True),
                },
            ),
            **error_responses(400, 401, 403, 404),
        },
    )
    def get(self, request, pk):
        query = HistoryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        activities, keep = plot_history(request.user, pk, query.validated_data)
        results = activity_serializer()(
            activities, many=True, context={"keep_detection": keep}
        ).data
        summary = PestSummarySerializer(pest_summary(activities, keep), many=True).data
        return Response({"results": results, "summary": summary})
