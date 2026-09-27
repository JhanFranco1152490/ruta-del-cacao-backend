from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .filters import AccountFilter
from .models import User
from .requests import request_id_from
from .user_serializers import AccountCreatedSerializer, AccountCreateSerializer, AccountSerializer
from .user_services import create_account, get_account, list_accounts


@extend_schema_view(
    list=extend_schema(
        responses={200: AccountSerializer(many=True), **error_responses(400, 401, 403)}
    ),
    retrieve=extend_schema(responses={200: AccountSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        request=AccountCreateSerializer,
        responses={201: AccountCreatedSerializer, **error_responses(400, 401, 403, 409)},
    ),
)
class AccountViewSet(GenericViewSet):
    # Estático a propósito, solo para que drf-spectacular infiera el modelo: el alcance real
    # (visible_users, según quien pregunta) se aplica en cada acción, no aquí.
    queryset = User.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "accounts.users_view",
        "retrieve": "accounts.users_view",
        "create": "accounts.users_create",
    }
    filterset_class = AccountFilter
    search_fields = ["identity_document", "first_name__unaccent", "last_name__unaccent", "email"]
    lookup_value_converter = "uuid"

    def list(self, request):
        page = self.paginate_queryset(self.filter_queryset(list_accounts(request.user)))
        return self.get_paginated_response(AccountSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(AccountSerializer(get_account(request.user, pk)).data)

    def create(self, request):
        serializer = AccountCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = create_account(request.user, serializer.validated_data, request_id_from(request))
        data = {
            **AccountSerializer(created.user).data,
            "activation_email_sent": created.activation_email_sent,
        }
        return Response(data, status=status.HTTP_201_CREATED)
