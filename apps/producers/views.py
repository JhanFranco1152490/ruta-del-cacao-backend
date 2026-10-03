from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import DuplicateDocument
from .filters import ProducerFilter
from .models import Producer
from .serializers import (
    ProducerConflictErrorSerializer,
    ProducerDeleteSerializer,
    ProducerDetailSerializer,
    ProducerListSerializer,
    ProducerSerializer,
    ProducerStatusSerializer,
    ProducerUpdateSerializer,
)
from .services import (
    change_producer_status,
    create_producer,
    delete_producer,
    get_producer,
    update_producer,
)


@extend_schema_view(
    # 400: filtro con un valor inválido; 404: página fuera de rango.
    list=extend_schema(
        responses={200: ProducerListSerializer(many=True), **error_responses(400, 401, 403, 404)}
    ),
    retrieve=extend_schema(
        responses={200: ProducerDetailSerializer, **error_responses(401, 403, 404)}
    ),
    create=extend_schema(
        request=ProducerSerializer,
        responses={
            201: ProducerDetailSerializer,
            409: ProducerConflictErrorSerializer,
            **error_responses(400, 401, 403),
        },
    ),
    partial_update=extend_schema(
        description=(
            "Edición parcial. Requiere `expected_version` (la versión que se leyó; si cambió "
            "responde 409) y al menos un campo editable más; si falta alguno responde 400."
        ),
        request=ProducerUpdateSerializer,
        responses={
            200: ProducerDetailSerializer,
            409: ProducerConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` del productor que se leyó.",
            )
        ],
        responses={
            204: None,
            409: ProducerConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    change_status=extend_schema(
        request=ProducerStatusSerializer,
        responses={200: ProducerDetailSerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
)
class ProducerViewSet(GenericViewSet):
    queryset = Producer.objects.all()
    serializer_class = ProducerSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "producers.view",
        "retrieve": "producers.view",
        "create": "producers.create",
        "partial_update": "producers.update",
        "destroy": "producers.delete",
        "change_status": "producers.change_status",
    }
    filterset_class = ProducerFilter
    # `unaccent` compara sin tildes en ambos lados: "perez" encuentra "Pérez" y viceversa.
    search_fields = [
        "identity_document",
        "first_name__unaccent",
        "last_name__unaccent",
        "member_code",
    ]
    lookup_value_converter = "uuid"

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(self.get_queryset()))
        return self.get_paginated_response(ProducerListSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(ProducerSerializer(get_producer(pk)).data)

    def create(self, request):
        serializer = ProducerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        producer = create_producer(serializer.validated_data)
        return Response(
            ProducerSerializer(producer).data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("producer-detail", args=[producer.pk])},
        )

    def partial_update(self, request, pk):
        serializer = ProducerUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        expected_version = data.pop("expected_version")
        return Response(ProducerSerializer(update_producer(pk, expected_version, data)).data)

    # Elimina un productor creado por error. La versión va en la URL: un cuerpo en DELETE no tiene
    # significado definido en HTTP y algunos intermediarios lo descartan. Sin conflicto de
    # versión ni dependientes importantes responde 204; con ellos, 409 y no se borra nada.
    def destroy(self, request, pk):
        serializer = ProducerDeleteSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        delete_producer(request.user, pk, serializer.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, pk):
        serializer = ProducerStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        producer = change_producer_status(
            pk, serializer.validated_data["expected_version"], serializer.validated_data["status"]
        )
        return Response(ProducerSerializer(producer).data)

    def handle_exception(self, exc):
        # Solo quien puede consultar productores ve cuál expediente ya tiene el documento.
        if isinstance(exc, DuplicateDocument) and not self.request.user.has_perm("producers.view"):
            exc.extra = {}
        return super().handle_exception(exc)
