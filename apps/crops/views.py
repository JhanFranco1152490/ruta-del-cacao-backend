from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleCharacterizationVersion
from .serializers import (
    CacaoVarietyCreateSerializer,
    CacaoVarietyListQuerySerializer,
    CacaoVarietyListSerializer,
    CacaoVarietySerializer,
    CacaoVarietyUpdateSerializer,
    PlotCharacterizationListQuerySerializer,
    PlotCharacterizationListSerializer,
    PlotCharacterizationSerializer,
    PlotCharacterizationWriteSerializer,
    StaleCharacterizationErrorSerializer,
)
from .services import (
    create_variety,
    get_characterization,
    list_characterizations,
    list_varieties,
    save_characterization,
    update_variety,
)


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
                description=(
                    "Busca en el nombre y en los nombres comunes, sin mayúsculas, tildes, "
                    "espacios ni guiones."
                ),
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


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las fichas de las parcelas de una finca del productor de la sesión, sin paginar: una "
            "finca tiene pocas parcelas. `farm` es obligatorio. Las parcelas sin ficha no "
            "aparecen, y una finca ajena devuelve la lista vacía."
        ),
        parameters=[
            OpenApiParameter("farm", str, required=True, description="La finca, por su `id`."),
        ],
        responses={200: PlotCharacterizationListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        description="La ficha de una parcela. 404 si la parcela es ajena o no tiene ficha.",
        responses={200: PlotCharacterizationSerializer, **error_responses(401, 403, 404)},
    ),
    update=extend_schema(
        description=(
            "Registra o reemplaza la ficha completa de la parcela. `expected_version` es `null` "
            "para registrar y la versión que se leyó para editar; si no coincide responde 409 "
            "`stale_version` con la ficha vigente (o `null`) en `current`. Si la ficha ya tiene "
            "exactamente ese contenido responde 200 sin subir la versión: es un reintento. Una "
            "variedad que no existe es un 400 en `fields.plantings`; una desactivada que no "
            "estaba en la ficha, 422 `variety_inactive`; una densidad mayor de 10.000 árboles/ha "
            "sobre el área declarada de la parcela, 422 `density_too_high`."
        ),
        request=PlotCharacterizationWriteSerializer,
        responses={
            200: PlotCharacterizationSerializer,
            201: PlotCharacterizationSerializer,
            409: StaleCharacterizationErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
)
class PlotCharacterizationViewSet(DomainValidationMixin, GenericViewSet):
    serializer_class = PlotCharacterizationSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    # Consultar la ficha va con la parcela. La asociación no tiene ese permiso: no lee las
    # parcelas ni las fichas de cada productor.
    action_permissions = {
        "list": "plots.view_plot",
        "retrieve": "plots.view_plot",
        "update": "crops.change_plotcharacterization",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = PlotCharacterizationListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        characterizations = list_characterizations(request.user, query.validated_data["farm"])
        return Response(PlotCharacterizationListSerializer({"results": characterizations}).data)

    def retrieve(self, request, pk):
        characterization = get_characterization(request.user, pk)
        return Response(PlotCharacterizationSerializer(characterization).data)

    def update(self, request, pk):
        serializer = PlotCharacterizationWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        _, created = save_characterization(request.user, pk, expected_version, data)
        # Se vuelve a leer con las filas y sus variedades, como la consulta.
        body = PlotCharacterizationSerializer(get_characterization(request.user, pk)).data
        if not created:
            return Response(body)
        return Response(
            body,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("plot-characterization-detail", args=[pk])},
        )

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con la ficha vigente; aquí se convierte en lo que la
        # interfaz necesita para resolverlo sin otra consulta.
        if isinstance(exc, StaleCharacterizationVersion):
            current = exc.current_characterization
            exc.extra = {
                "current": (
                    None if current is None else PlotCharacterizationSerializer(current).data
                )
            }
        return super().handle_exception(exc)
