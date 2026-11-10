from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import StaleBuyerVersion
from .serializers import (
    BuyerConflictErrorSerializer,
    BuyerCreateSerializer,
    BuyerDeleteSerializer,
    BuyerListQuerySerializer,
    BuyerListSerializer,
    BuyerSerializer,
    BuyerUpdateSerializer,
)
from .services import create_buyer, delete_buyer, get_buyer, list_buyers, update_buyer


@extend_schema_view(
    list=extend_schema(
        description=(
            "El directorio completo de compradores del productor de la sesión, activos e "
            "inactivos, ordenado por nombre y sin paginar: la búsqueda y los filtros corren en el "
            "dispositivo. No depende de las fincas de quien consulta."
        ),
        parameters=[
            OpenApiParameter(
                "producer",
                OpenApiTypes.UUID,
                description="Solo la cuenta técnica: el productor cuyo directorio se quiere ver.",
            ),
        ],
        responses={200: BuyerListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(responses={200: BuyerSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Registra un comprador en el directorio del productor de la sesión. `producer_id` "
            "solo lo envía la cuenta técnica, y para ella es obligatorio. Pide un teléfono o un "
            "correo. Si ya hay uno con el mismo tipo y número de documento, 409 "
            "`duplicate_document` con el existente en `existing`."
        ),
        request=BuyerCreateSerializer,
        responses={
            201: BuyerSerializer,
            409: BuyerConflictErrorSerializer,
            **error_responses(400, 401, 403, 422),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edición parcial, incluida la activación o desactivación con `is_active`. Todo se "
            "puede cambiar, también el documento. Requiere `expected_version`; si el comprador "
            "cambió, 409 `stale_version` con el vigente en `current`. El resultado debe seguir "
            "teniendo un teléfono o un correo."
        ),
        request=BuyerUpdateSerializer,
        responses={
            200: BuyerSerializer,
            409: BuyerConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina un comprador creado por error. Requiere `expected_version` en la URL. Si "
            "algún registro lo usa (sus ventas), 409 `buyer_has_records`: se desactiva en su "
            "lugar. El historial del comprador se conserva."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` del comprador que se leyó.",
            )
        ],
        responses={
            204: None,
            409: BuyerConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class BuyerViewSet(GenericViewSet):
    serializer_class = BuyerSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "buyers.view_buyer",
        "retrieve": "buyers.view_buyer",
        "create": "buyers.add_buyer",
        "partial_update": "buyers.change_buyer",
        "destroy": "buyers.delete_buyer",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = BuyerListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        buyers = list_buyers(request.user, producer=query.validated_data.get("producer"))
        return Response({"results": BuyerSerializer(buyers, many=True).data})

    def retrieve(self, request, pk):
        return Response(BuyerSerializer(get_buyer(request.user, pk)).data)

    def create(self, request):
        serializer = BuyerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        buyer = create_buyer(request.user, serializer.to_model_data())
        return Response(
            BuyerSerializer(buyer).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("buyer-detail", args=[buyer.pk])},
        )

    def partial_update(self, request, pk):
        serializer = BuyerUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.to_model_data()
        expected_version = data.pop("expected_version")
        buyer = update_buyer(request.user, pk, expected_version, data)
        return Response(BuyerSerializer(buyer).data)

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP.
        serializer = BuyerDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_buyer(request.user, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    def handle_exception(self, exc):
        if isinstance(exc, StaleBuyerVersion):
            exc.extra = {"current": BuyerSerializer(exc.current_buyer).data}
        return super().handle_exception(exc)
