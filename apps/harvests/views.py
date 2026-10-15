from django.urls import reverse
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import HarvestConflictErrorSerializer, HarvestCreateSerializer, HarvestSerializer
from .services.create import create_harvest
from .services.queries import get_harvest


@extend_schema_view(
    retrieve=extend_schema(
        responses={200: HarvestSerializer, **error_responses(401, 403, 404)},
    ),
    create=extend_schema(
        description=(
            "Registra una cosecha en una parcela con ficha y siembras. `id` lo genera el "
            "dispositivo: reenviar el mismo `id` con los mismos datos responde 200 con la "
            "cosecha ya creada; con otros datos, 409 `harvest_id_conflict`. La parcela sin "
            "siembras es 422 `plot_not_characterized`; una variedad que no está en la ficha, 422 "
            "`variety_not_in_plot`; un recolector que no cumple, 422 `collector_not_available`. "
            "Una parcela o finca inactivas no impiden registrar."
        ),
        request=HarvestCreateSerializer,
        responses={
            200: HarvestSerializer,
            201: HarvestSerializer,
            409: HarvestConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
)
class HarvestViewSet(GenericViewSet):
    serializer_class = HarvestSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "retrieve": "harvests.view_harvest",
        "create": "harvests.add_harvest",
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def retrieve(self, request, pk):
        return Response(HarvestSerializer(get_harvest(request.user, pk)).data)

    def create(self, request):
        serializer = HarvestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        harvest, created = create_harvest(request.user, serializer.validated_data)
        data = HarvestSerializer(harvest).data
        if not created:
            return Response(data)
        return Response(
            data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("harvest-detail", args=[harvest.pk])},
        )
