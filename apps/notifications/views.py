from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.schema import error_responses

from .models import Notification
from .serializers import InboxQuerySerializer, NotificationSerializer, UnreadCountSerializer
from .services.queries import inbox, unread_count


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
