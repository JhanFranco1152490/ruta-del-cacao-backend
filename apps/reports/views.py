from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from .request_serializers import AssociationReportQuerySerializer, ProducerReportQuerySerializer
from .serializers import ReportSerializer
from .services import association_report, producer_report

PRODUCER_DESCRIPTION = (
    "Un reporte de la unidad productiva, una fila por registro: `production` (cosechas), "
    "`quality` (lotes clasificados o descartados en el periodo), `inventory` (existencias de hoy, "
    "sin periodo), `sales` (líneas de las ventas registradas, con precio) o `traceability` (un "
    "lote por fila, de la cosecha a la venta). Cada tipo pide además el permiso de consulta de su "
    "módulo. `from` y `to` incluidos, hasta 366 días; `farm`, `plot` y `lot` acotan (404 si no "
    "están en el alcance) y `producer` solo lo usa la cuenta técnica. Las columnas describen las "
    "filas: kg y porcentajes como texto, pesos y conteos como enteros. Más de 5.000 filas: "
    "`report_too_large`."
)
ASSOCIATION_DESCRIPTION = (
    "Un reporte de la asociación, una fila por finca: `production`, `quality` o `sales`, con "
    "las mismas cifras del panel de la asociación. Salen todas las fincas de los filtros, también "
    "en 0, salvo las inactivas o de productores inactivos sin cifras; sin ninguna cifra, sin "
    "filas. Nada por parcela, por lote, de existencias ni en pesos. `municipality` es un código "
    "de Norte de Santander; `producer` y `farm`, 404 si no existen o no coinciden."
)


class ProducerReportView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "reports.view_producer_reports"

    @extend_schema(
        description=PRODUCER_DESCRIPTION,
        parameters=[ProducerReportQuerySerializer],
        responses={200: ReportSerializer, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        query = ProducerReportQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        report = producer_report(request.user, query.validated_data)
        return Response(ReportSerializer(report).data)


class AssociationReportView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "reports.view_association_reports"

    @extend_schema(
        description=ASSOCIATION_DESCRIPTION,
        parameters=[AssociationReportQuerySerializer],
        responses={200: ReportSerializer, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        query = AssociationReportQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        report = association_report(request.user, query.validated_data)
        return Response(ReportSerializer(report).data)
