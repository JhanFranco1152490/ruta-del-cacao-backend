from django.core.exceptions import ValidationError as DjangoValidationError
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import (
    CacaoVarietyCreateSerializer,
    CacaoVarietyListQuerySerializer,
    CacaoVarietyListSerializer,
    CacaoVarietySerializer,
    CacaoVarietyUpdateSerializer,
)
from .services import create_variety, list_varieties, update_variety


class DomainValidationMixin:
    def handle_exception(self, exc):
        # El modelo valida lo que el serializer no sabe (un nombre hecho solo de guiones queda
        # vacío al compararlo): se responde como cualquier otro error de campo.
        if isinstance(exc, DjangoValidationError) and hasattr(exc, "error_dict"):
            exc = ValidationError(exc.message_dict)
        return super().handle_exception(exc)


@extend_schema_view(
    list=extend_schema(
        description=(
            "El catálogo común de variedades de cacao, ordenado por nombre y sin paginar: el "
            "formulario de la ficha las necesita todas, también sin conexión. Basta con tener "
            "sesión."
        ),
        parameters=[
            OpenApiParameter("is_active", bool, description="Solo activas o solo inactivas."),
            OpenApiParameter(
                "search",
                str,
                description="Busca en el nombre sin mayúsculas, tildes, espacios ni guiones.",
            ),
        ],
        responses={200: CacaoVarietyListSerializer, **error_responses(400, 401)},
    ),
    create=extend_schema(
        description=(
            "Registra una variedad. Un nombre que ya existe, aunque se escriba distinto "
            "(`CCN 51` y `ccn-51`), responde 409 `duplicate_variety_name`."
        ),
        request=CacaoVarietyCreateSerializer,
        responses={201: CacaoVarietySerializer, **error_responses(400, 401, 403, 409)},
    ),
    partial_update=extend_schema(
        description=(
            "Edita el nombre o la descripción, o activa y desactiva con `is_active`. Desactivar "
            "no cambia las fichas que ya la usan: solo deja de ofrecerse para siembras nuevas."
        ),
        request=CacaoVarietyUpdateSerializer,
        responses={200: CacaoVarietySerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
)
class CacaoVarietyViewSet(DomainValidationMixin, GenericViewSet):
    serializer_class = CacaoVarietySerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "create": "crops.manage_cacaovariety",
        "partial_update": "crops.manage_cacaovariety",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def get_permissions(self):
        # Son datos de referencia sin información personal, que cualquier formulario que elija
        # una variedad necesita: consultarlos solo pide sesión, como el catálogo de municipios.
        if self.action == "list":
            return [IsAuthenticated()]
        return super().get_permissions()

    def list(self, request):
        # Se pasa un dict y no el QueryDict: con un QueryDict, DRF toma un booleano ausente
        # como `false` y filtraría las activas sin que nadie lo pidiera.
        query = CacaoVarietyListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        varieties = list_varieties(
            is_active=query.validated_data.get("is_active"),
            search=query.validated_data.get("search"),
        )
        return Response(CacaoVarietyListSerializer({"results": varieties}).data)

    def create(self, request):
        serializer = CacaoVarietyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        variety = create_variety(request.user, serializer.validated_data)
        return Response(CacaoVarietySerializer(variety).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk):
        serializer = CacaoVarietyUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        variety = update_variety(request.user, pk, serializer.validated_data)
        return Response(CacaoVarietySerializer(variety).data)
