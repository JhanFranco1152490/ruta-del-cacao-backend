from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.ordering import ProducerOrderingFilter
from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from ..models import User
from ..requests import request_id_from
from ..throttles import ActivationResendThrottle
from .filters import AccountFilter
from .serializers import (
    AccountCreatedSerializer,
    AccountCreateSerializer,
    AccountRoleIdsSerializer,
    AccountSerializer,
    AccountStatusSerializer,
    AccountUpdateSerializer,
    ActivationEmailSentSerializer,
)
from .services import (
    create_account,
    delete_account,
    get_account,
    list_accounts,
    set_account_roles,
    set_account_status,
    update_account,
)
from .services import resend_activation as resend_activation_service


@extend_schema_view(
    list=extend_schema(
        responses={200: AccountSerializer(many=True), **error_responses(400, 401, 403)}
    ),
    retrieve=extend_schema(responses={200: AccountSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        request=AccountCreateSerializer,
        responses={201: AccountCreatedSerializer, **error_responses(400, 401, 403, 409)},
    ),
    partial_update=extend_schema(
        request=AccountUpdateSerializer,
        responses={200: AccountSerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
    roles=extend_schema(
        request=AccountRoleIdsSerializer,
        responses={200: AccountSerializer, **error_responses(400, 401, 403, 404)},
    ),
    destroy=extend_schema(responses={204: None, **error_responses(401, 403, 404, 409)}),
    change_status=extend_schema(
        request=AccountStatusSerializer,
        responses={200: AccountSerializer, **error_responses(400, 401, 403, 404, 409)},
    ),
    resend_activation=extend_schema(
        request=None,
        responses={200: ActivationEmailSentSerializer, **error_responses(401, 403, 404, 409, 429)},
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
        "partial_update": "accounts.users_update",
        "roles": "accounts.users_update",
        "destroy": "accounts.users_delete",
        "change_status": "accounts.users_change_status",
        "resend_activation": "accounts.users_update",
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, ProducerOrderingFilter]
    filterset_class = AccountFilter
    search_fields = ["identity_document", "first_name__unaccent", "last_name__unaccent", "email"]
    # Un valor que no está aquí se ignora en vez de dar 400 (comportamiento propio de
    # `OrderingFilter`): a diferencia de un filtro con significado de negocio (`status`), un
    # `ordering` inválido no da resultados equivocados, solo cae al orden por defecto.
    ordering_fields = ["email", "first_name", "last_name", "date_joined", "producer"]
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

    def partial_update(self, request, pk):
        serializer = AccountUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_account(
            request.user, pk, serializer.validated_data, request_id_from(request)
        )
        return Response(AccountSerializer(user).data)

    def destroy(self, request, pk):
        delete_account(request.user, pk, request_id_from(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["put"], url_path="roles")
    def roles(self, request, pk):
        serializer = AccountRoleIdsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = set_account_roles(
            request.user, pk, serializer.validated_data["role_ids"], request_id_from(request)
        )
        return Response(AccountSerializer(user).data)

    @action(detail=True, methods=["patch"], url_path="status")
    def change_status(self, request, pk):
        serializer = AccountStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = set_account_status(
            request.user, pk, serializer.validated_data["status"], request_id_from(request)
        )
        return Response(AccountSerializer(user).data)

    @action(
        detail=True,
        methods=["post"],
        url_path="resend-activation",
        throttle_classes=[ActivationResendThrottle],
    )
    def resend_activation(self, request, pk):
        activation_email_sent = resend_activation_service(request.user, pk)
        return Response(
            ActivationEmailSentSerializer({"activation_email_sent": activation_email_sent}).data
        )
