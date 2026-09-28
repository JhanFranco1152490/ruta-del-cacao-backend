from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission, HasPermission
from apps.common.schema import error_responses

from ..models import Role
from ..requests import request_id_from
from ..scope import visible_roles
from .filters import RoleFilter
from .serializers import (
    PermissionListSerializer,
    RoleCreateSerializer,
    RoleSerializer,
    RoleUpdateSerializer,
)
from .services import create_role, delete_role, get_role, permission_catalog, update_role


@extend_schema_view(
    list=extend_schema(
        responses={200: RoleSerializer(many=True), **error_responses(401, 403, 404)}
    ),
    retrieve=extend_schema(responses={200: RoleSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        request=RoleCreateSerializer,
        responses={201: RoleSerializer, **error_responses(400, 401, 403, 409)},
    ),
    partial_update=extend_schema(
        request=RoleUpdateSerializer,
        responses={200: RoleSerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
    destroy=extend_schema(responses={204: None, **error_responses(401, 403, 404, 409)}),
)
class RoleViewSet(GenericViewSet):
    # Estático a propósito, solo para que drf-spectacular infiera el modelo: el alcance real
    # (visible_roles, según quien pregunta) se aplica en list() y en cada acción, no aquí.
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "accounts.roles_view",
        "retrieve": "accounts.roles_view",
        "create": "accounts.roles_manage",
        "partial_update": "accounts.roles_manage",
        "destroy": "accounts.roles_manage",
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RoleFilter
    # `unaccent` compara sin tildes, igual que la búsqueda de cuentas y de productores.
    search_fields = ["name__unaccent"]
    # Un valor que no está aquí se ignora en vez de dar 400 (ver el mismo comentario en
    # `user_views.py`).
    ordering_fields = ["name", "kind"]
    lookup_value_converter = "uuid"

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(visible_roles(request.user)))
        return self.get_paginated_response(RoleSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(RoleSerializer(get_role(request.user, pk)).data)

    def create(self, request):
        serializer = RoleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = create_role(request.user, serializer.validated_data, request_id_from(request))
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk):
        serializer = RoleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        role = update_role(request.user, pk, serializer.validated_data, request_id_from(request))
        return Response(RoleSerializer(role).data)

    def destroy(self, request, pk):
        delete_role(request.user, pk, request_id_from(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionCatalogView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.roles_view"

    @extend_schema(responses={200: PermissionListSerializer, **error_responses(401, 403)})
    def get(self, request):
        return Response(
            PermissionListSerializer({"results": permission_catalog(request.user)}).data
        )
