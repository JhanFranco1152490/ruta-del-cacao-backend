from django.urls import reverse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import HarvestAlreadyInLot, StaleLotVersion
from .serializers import LotConflictErrorSerializer, LotCreateSerializer, LotSerializer
from .services.create import create_lot
from .services.queries import get_lot


@extend_schema_view(
    retrieve=extend_schema(responses={200: LotSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Conforma el lote de una cosecha y le asigna su código. Solo en línea: el código lo "
            "asigna el servidor. `id` lo genera el dispositivo: reenviar el mismo `id` para la "
            "misma cosecha responde 200 con el lote ya creado. Una cosecha que ya forma un lote "
            "es 409 `harvest_already_in_lot`, con ese lote en `current`."
        ),
        request=LotCreateSerializer,
        responses={
            200: LotSerializer,
            201: LotSerializer,
            409: LotConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class LotViewSet(GenericViewSet):
    serializer_class = LotSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "retrieve": "lots.view_lot",
        "create": "lots.add_lot",
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def retrieve(self, request, pk):
        return Response(LotSerializer(get_lot(request.user, pk)).data)

    def create(self, request):
        serializer = LotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot, created = create_lot(request.user, serializer.validated_data)
        data = LotSerializer(lot).data
        if not created:
            return Response(data)
        return Response(
            data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("lot-detail", args=[lot.pk])},
        )

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con el lote del dominio; aquí se convierte en lo que el
        # cliente necesita para mostrar el vigente sin otra consulta.
        if isinstance(exc, HarvestAlreadyInLot):
            exc.extra = {"current": LotSerializer(exc.current_lot).data}
        elif isinstance(exc, StaleLotVersion):
            exc.extra = {"current": LotSerializer(exc.current_lot).data}
        return super().handle_exception(exc)
