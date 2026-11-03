from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import (
    LotQualitySerializer,
    QualityListQuerySerializer,
    QualitySummaryQuerySerializer,
    QualitySummarySerializer,
)
from .services.queries import get_quality_lot, list_quality_lots, quality_summary

EVALUATE = "quality.evaluate_lot"
PRODUCER_PARAMETER = OpenApiParameter("producer", str, description="Solo para la cuenta técnica.")


@extend_schema_view(
    list=extend_schema(
        description=(
            "Los lotes de calidad de las fincas que la cuenta alcanza, paginados. `view` elige "
            "cuáles: `to_evaluate` (por defecto, los Seco, del que se secó primero), `evaluated` "
            "(del que se evaluó primero) o `closed` (Clasificado y Descartado, del más reciente). "
            "`search` busca una parte del código, sin distinguir mayúsculas."
        ),
        parameters=[QualityListQuerySerializer, PRODUCER_PARAMETER],
        responses={200: LotQualitySerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
    retrieve=extend_schema(
        description="La calidad de un lote Seco o posterior. Un lote anterior a Seco es 404.",
        responses={200: LotQualitySerializer, **error_responses(401, 403, 404)},
    ),
)
class QualityViewSet(GenericViewSet):
    serializer_class = LotQualitySerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": EVALUATE,
        "retrieve": EVALUATE,
        "summary": EVALUATE,
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = QualityListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_quality_lots(request.user, query.validated_data))
        return self.get_paginated_response(LotQualitySerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(LotQualitySerializer(get_quality_lot(request.user, pk)).data)

    @extend_schema(
        description=(
            "Las cifras de la pantalla de calidad: cuántos lotes y kilos secos esperan su "
            "evaluación, cuántos esperan clasificarse y cuántos se descartaron este mes. Con los "
            "mismos filtros de la lista menos `view`."
        ),
        parameters=[QualitySummaryQuerySerializer, PRODUCER_PARAMETER],
        responses={200: QualitySummarySerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        query = QualitySummaryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(
            QualitySummarySerializer(quality_summary(request.user, query.validated_data)).data
        )
