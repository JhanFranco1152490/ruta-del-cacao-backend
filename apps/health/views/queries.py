from drf_spectacular.utils import (
    OpenApiParameter,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.activity_representation import activity_serializer
from apps.common.pagination import StandardPagination
from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from ..serializers import (
    HistoryQuerySerializer,
    PestSummarySerializer,
    WaitingDetectionListSerializer,
    WaitingQuerySerializer,
)
from ..services.history import monitoring_history, pest_summary
from ..services.waiting import detections_without_control, dismiss_control


class HistoryPagination(StandardPagination):
    """La paginación común, más el resumen por plaga de la parcela, calculado con todas las
    páginas: si se calculara con la que se ve, la "última incidencia" cambiaría al pasar de
    página."""

    def get_paginated_response(self, data, summary):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
                "summary": summary,
            }
        )


class HistoryView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.view_agriculturalactivity"

    @extend_schema(
        operation_id="phytosanitary_history_retrieve",
        description=(
            "Los monitoreos realizados de todo lo que alcanza la cuenta, del más reciente al más "
            "antiguo, con la forma de la actividad y su `monitoring`. `farm` y `plot` los acotan: "
            "una finca o una parcela que la cuenta no alcanza es 404. `from` y `to` filtran por "
            "la fecha de realización; `pest_disease` u `other=true` dejan solo los monitoreos "
            "donde se detectó, con esa detección. Con `plot`, `summary` trae por plaga (y por "
            "cada texto de Otra) la última incidencia y la anterior del mismo tipo de muestreo, "
            "calculadas con todas las páginas; sin `plot` viene vacío, porque comparar parcelas "
            "distintas no dice si una plaga sube o baja. `producer` solo lo usa la cuenta "
            "técnica."
        ),
        parameters=[
            OpenApiParameter("farm", str, description="Una finca."),
            OpenApiParameter("plot", str, description="Una parcela."),
            OpenApiParameter("producer", str, description="Solo para la cuenta técnica."),
            OpenApiParameter("from", str, description="Fecha inicial (incluida)."),
            OpenApiParameter("to", str, description="Fecha final (incluida)."),
            OpenApiParameter("pest_disease", str, description="Una plaga o enfermedad."),
            OpenApiParameter("other", bool, description="Solo las detecciones de Otra."),
        ],
        responses={
            200: inline_serializer(
                "PhytosanitaryHistory",
                fields={
                    "count": serializers.IntegerField(),
                    "next": serializers.URLField(allow_null=True),
                    "previous": serializers.URLField(allow_null=True),
                    "results": activity_serializer()(many=True),
                    "summary": PestSummarySerializer(many=True),
                },
            ),
            **error_responses(400, 401, 403, 404),
        },
    )
    def get(self, request):
        query = HistoryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        filters = query.validated_data
        activities, keep = monitoring_history(request.user, filters)
        paginator = HistoryPagination()
        if filters.get("plot") is not None:
            # Una parcela tiene pocos monitoreos: se leen todos para que el resumen cuente con
            # todos y no con la página.
            everything = list(activities)
            summary = PestSummarySerializer(pest_summary(everything, keep), many=True).data
            page = paginator.paginate_queryset(everything, request, view=self)
        else:
            summary = []
            page = paginator.paginate_queryset(activities, request, view=self)
        results = activity_serializer()(page, many=True, context={"keep_detection": keep}).data
        return paginator.get_paginated_response(results, summary)


class DetectionsWithoutControlView(APIView):
    # Solo quien puede programar controles: es quien puede resolver lo que el aviso señala.
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.add_agriculturalactivity"

    @extend_schema(
        operation_id="phytosanitary_detections_without_control_list",
        description=(
            "Las detecciones en que alguien pidió que le programen un control y nadie lo ha "
            "atendido (ni programado ni marcado como que no lo requiere), del monitoreo más "
            "antiguo al más reciente, en las fincas que alcanza la cuenta. Una detección con "
            "«Ninguno por ahora» no está: no se pidió nada. Sin fecha mínima ni paginar. Pide el "
            "permiso de programar. La cuenta técnica puede acotar con `producer`."
        ),
        parameters=[OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")],
        responses={200: WaitingDetectionListSerializer, **error_responses(400, 401, 403)},
    )
    def get(self, request):
        query = WaitingQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        detections = detections_without_control(request.user, query.validated_data.get("producer"))
        return Response(WaitingDetectionListSerializer({"results": detections}).data)


class NoControlNeededView(APIView):
    # Lo decide quien puede programar controles, como lo atiende.
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.add_agriculturalactivity"

    @extend_schema(
        operation_id="phytosanitary_detections_no_control_needed",
        request=None,
        description=(
            "Decide que una detección no requiere control: sale del aviso de las que esperan uno "
            "y queda registrado quién lo decidió. Repetirlo responde 204 sin cambiar quién lo "
            "decidió primero. Pide el permiso de programar."
        ),
        responses={204: None, **error_responses(401, 403, 404)},
    )
    def post(self, request, pk):
        dismiss_control(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)
