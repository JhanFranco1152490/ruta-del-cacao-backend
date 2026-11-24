from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .request_serializers import AuditLogQuerySerializer, AuditOptionsQuerySerializer
from .serializers import AuditEntrySerializer, AuditOptionsSerializer
from .services.log import audit_log_rows, audit_options, describe_rows

PRODUCER_PARAMETER = OpenApiParameter(
    "producer", str, description="Solo para la cuenta técnica, y obligatorio para ella."
)


@extend_schema_view(
    list=extend_schema(
        description=(
            "La bitácora de cambios de la unidad productiva, de lo más reciente a lo más "
            "antiguo, paginada: cada modificación con quién la hizo, cuándo, el registro "
            "afectado (también si ya se eliminó) y el valor anterior y el nuevo de cada campo. "
            "Un dato personal o lo que no se muestra como valor trae `hidden` y sin valores; lo "
            "guardado antes de que el historial los tuviera, `not_recorded`. `from` y `to` son "
            "fechas locales, opcionales; `actor` es una cuenta del productor (404 si no) y "
            "`record_type`, uno de los tipos de `/options`. Solo el Productor y la cuenta "
            "técnica."
        ),
        parameters=[AuditLogQuerySerializer, PRODUCER_PARAMETER],
        responses={200: AuditEntrySerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
)
class AuditLogViewSet(GenericViewSet):
    serializer_class = AuditEntrySerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {"list": "audit.view_audit_log", "options": "audit.view_audit_log"}
    filter_backends = []

    def list(self, request):
        query = AuditLogQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(audit_log_rows(request.user, query.validated_data))
        return self.get_paginated_response(
            AuditEntrySerializer(describe_rows(page), many=True).data
        )

    @extend_schema(
        description=(
            "Lo que se ofrece para filtrar la bitácora: las cuentas del productor, activas e "
            "inactivas, por nombre, y los tipos de registro con su etiqueta, en orden."
        ),
        parameters=[PRODUCER_PARAMETER],
        responses={200: AuditOptionsSerializer, **error_responses(400, 401, 403, 404)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def options(self, request):
        query = AuditOptionsQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        return Response(
            AuditOptionsSerializer(audit_options(request.user, query.validated_data)).data
        )
