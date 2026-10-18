from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.schema import error_responses

from .models import Notification
from .serializers import (
    DismissedCountSerializer,
    InboxQuerySerializer,
    NotificationSerializer,
    UnreadCountSerializer,
    UpdatedCountSerializer,
)
from .services.queries import inbox, unread_count
from .services.update import dismiss, dismiss_read, mark_all_read, mark_read, restore


@extend_schema_view(
    list=extend_schema(
        description=(
            "Las notificaciones de la cuenta, sin las eliminadas y solo de lo que alcanza hoy: "
            "primero las críticas sin leer y después de la más reciente a la más antigua. "
            "`activity` viene como está hoy, con la forma del calendario. `unread=true` deja "
            "solo las no leídas."
        ),
        parameters=[OpenApiParameter("unread", bool, description="Solo las no leídas.")],
        responses={200: NotificationSerializer(many=True), **error_responses(400, 401)},
    ),
)
class NotificationViewSet(GenericViewSet):
    # Cada cuenta ve solo sus avisos: lo que filtra es el alcance, no un permiso propio.
    serializer_class = NotificationSerializer
    lookup_value_converter = "uuid"
    # Solo para que el esquema sepa de qué modelo es: lo que se lista sale de `inbox`.
    queryset = Notification.objects.none()

    def list(self, request):
        query = InboxQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        notifications = inbox(request.user, unread_only=query.validated_data["unread"])
        page = self.paginate_queryset(notifications)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    @extend_schema(
        description="Cuántas notificaciones sin leer ve la cuenta, para el número de la campana.",
        responses={200: UnreadCountSerializer, **error_responses(401)},
    )
    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        return Response({"count": unread_count(request.user)})

    @extend_schema(
        description=(
            "Marca la notificación como leída. Si ya lo estaba, conserva la hora de la primera "
            "lectura. Una eliminada, ajena o de una finca que la cuenta ya no alcanza es 404."
        ),
        request=None,
        responses={204: None, **error_responses(401, 403, 404)},
    )
    @action(detail=True, methods=["post"])
    def read(self, request, pk):
        mark_read(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description="Marca como leídas todas las no leídas que la cuenta ve. Dice cuántas.",
        request=None,
        responses={200: UpdatedCountSerializer, **error_responses(401, 403)},
    )
    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        return Response({"updated": mark_all_read(request.user)})

    @extend_schema(
        description=(
            "Elimina la notificación de la bandeja. El aviso no vuelve aunque su condición siga: "
            "la siguiente evaluación sabe que ya se dio. Si ya estaba eliminada, no cambia nada."
        ),
        responses={204: None, **error_responses(401, 403, 404)},
    )
    def destroy(self, request, pk):
        dismiss(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description="Deshace la eliminación: la notificación vuelve a la bandeja.",
        request=None,
        responses={204: None, **error_responses(401, 403, 404)},
    )
    @action(detail=True, methods=["post"])
    def restore(self, request, pk):
        restore(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description="Elimina todas las leídas que la cuenta ve. Dice cuántas.",
        request=None,
        responses={200: DismissedCountSerializer, **error_responses(401, 403)},
    )
    @action(detail=False, methods=["post"], url_path="dismiss-read")
    def dismiss_read(self, request):
        return Response({"dismissed": dismiss_read(request.user)})
