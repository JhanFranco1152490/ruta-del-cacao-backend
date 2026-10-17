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
    PostharvestFacilityConflictErrorSerializer,
    PostharvestFacilityCreateSerializer,
    PostharvestFacilityListQuerySerializer,
    PostharvestFacilityListSerializer,
    PostharvestFacilitySerializer,
)
from .services import create_facility, get_facility, list_facilities


@extend_schema_view(
    list=extend_schema(
        description=(
            "Los cajones de fermentación y las marquesinas de secado de las fincas que alcanza la "
            "sesión, activos e inactivos, sin paginar: la finca y los filtros se eligen en el "
            "dispositivo. Primero los cajones y después las marquesinas, cada uno por nombre."
        ),
        parameters=[
            OpenApiParameter(
                "producer",
                OpenApiTypes.UUID,
                description="Solo la cuenta técnica: el productor cuyos elementos se quiere ver.",
            ),
        ],
        responses={200: PostharvestFacilityListSerializer, **error_responses(400, 401, 403)},
    ),
    retrieve=extend_schema(
        responses={200: PostharvestFacilitySerializer, **error_responses(401, 403, 404)}
    ),
    create=extend_schema(
        description=(
            "Registra un cajón o una marquesina en una finca que la sesión alcanza; queda "
            "Disponible. Si ya hay uno con el mismo nombre en la finca, sin importar el tipo, 409 "
            "`duplicate_facility_name` con el existente en `existing`. Una finca inactiva, 422 "
            "`farm_inactive`."
        ),
        request=PostharvestFacilityCreateSerializer,
        responses={
            201: PostharvestFacilitySerializer,
            409: PostharvestFacilityConflictErrorSerializer,
            **error_responses(400, 401, 403, 404, 422),
        },
    ),
)
class PostharvestFacilityViewSet(GenericViewSet):
    serializer_class = PostharvestFacilitySerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "facilities.view_postharvestfacility",
        "retrieve": "facilities.view_postharvestfacility",
        "create": "facilities.add_postharvestfacility",
    }
    filter_backends = []
    pagination_class = None
    lookup_value_converter = "uuid"

    def list(self, request):
        query = PostharvestFacilityListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        facilities = list_facilities(request.user, producer=query.validated_data.get("producer"))
        return Response({"results": PostharvestFacilitySerializer(facilities, many=True).data})

    def retrieve(self, request, pk):
        return Response(PostharvestFacilitySerializer(get_facility(request.user, pk)).data)

    def create(self, request):
        serializer = PostharvestFacilityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        facility = create_facility(request.user, serializer.validated_data)
        return Response(
            PostharvestFacilitySerializer(facility).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("postharvest-facility-detail", args=[facility.pk])},
        )
