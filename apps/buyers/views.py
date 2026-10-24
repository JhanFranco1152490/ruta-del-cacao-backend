from django.urls import reverse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .serializers import (
    BuyerConflictErrorSerializer,
    BuyerCreateSerializer,
    BuyerListQuerySerializer,
    BuyerListSerializer,
    BuyerSerializer,
)
from .services import create_buyer, get_buyer, list_buyers


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
)
class BuyerViewSet(GenericViewSet):
    serializer_class = BuyerSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "buyers.view_buyer",
        "retrieve": "buyers.view_buyer",
        "create": "buyers.add_buyer",
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
