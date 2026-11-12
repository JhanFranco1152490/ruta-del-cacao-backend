from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from .exporters import EXPORTERS, export
from .request_serializers import (
    AssociationReportExportQuerySerializer,
    AssociationReportQuerySerializer,
    ProducerReportExportQuerySerializer,
    ProducerReportQuerySerializer,
)
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
EXPORT_DESCRIPTION = (
    " Como archivo (`file`: `pdf`, `xlsx` o `csv`), con el tipo de reporte, los filtros y la "
    "fecha de generación. Sin filas: `report_empty`. El PDF admite hasta 2.000 filas "
    "(`report_too_large`); Excel y CSV, las del reporte."
)
FILE_RESPONSES = {
    (200, exporter.content_type.split(";")[0]): OpenApiTypes.BINARY
    for exporter in EXPORTERS.values()
}


class ReportView(APIView):
    """Lo común a las cuatro rutas: el permiso, la consulta validada y el reporte armado."""

    permission_classes = [IsAuthenticated, HasPermission]
    query_class = None
    build = None

    def report(self, request):
        query = self.query_class(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return self.build(request.user, query.validated_data), query.validated_data


class ReportFileView(ReportView):
    def get(self, request):
        report, query = self.report(request)
        exported = export(report, query["file"])
        response = HttpResponse(exported.content, content_type=exported.content_type)
        response["Content-Disposition"] = f'attachment; filename="{exported.file_name}"'
        # El navegador no adivina otro tipo que el del formato pedido.
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ProducerReportView(ReportView):
    required_permission = "reports.view_producer_reports"
    query_class = ProducerReportQuerySerializer
    build = staticmethod(producer_report)

    @extend_schema(
        description=PRODUCER_DESCRIPTION,
        parameters=[ProducerReportQuerySerializer],
        responses={200: ReportSerializer, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        report, _ = self.report(request)
        return Response(ReportSerializer(report).data)


class AssociationReportView(ReportView):
    required_permission = "reports.view_association_reports"
    query_class = AssociationReportQuerySerializer
    build = staticmethod(association_report)

    @extend_schema(
        description=ASSOCIATION_DESCRIPTION,
        parameters=[AssociationReportQuerySerializer],
        responses={200: ReportSerializer, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        report, _ = self.report(request)
        return Response(ReportSerializer(report).data)


class ProducerReportFileView(ReportFileView):
    required_permission = "reports.view_producer_reports"
    query_class = ProducerReportExportQuerySerializer
    build = staticmethod(producer_report)

    @extend_schema(
        description=PRODUCER_DESCRIPTION + EXPORT_DESCRIPTION,
        parameters=[ProducerReportExportQuerySerializer],
        responses={**FILE_RESPONSES, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        return super().get(request)


class AssociationReportFileView(ReportFileView):
    required_permission = "reports.view_association_reports"
    query_class = AssociationReportExportQuerySerializer
    build = staticmethod(association_report)

    @extend_schema(
        description=ASSOCIATION_DESCRIPTION + EXPORT_DESCRIPTION,
        parameters=[AssociationReportExportQuerySerializer],
        responses={**FILE_RESPONSES, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        return super().get(request)
