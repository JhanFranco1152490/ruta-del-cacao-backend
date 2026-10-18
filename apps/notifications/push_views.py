from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.schema import error_responses

from .push_serializers import (
    PushConfigSerializer,
    PushSubscriptionCreateSerializer,
    PushSubscriptionRemoveSerializer,
    PushSubscriptionSerializer,
)
from .services.subscriptions import public_key, subscribe, unsubscribe


class PushConfigView(APIView):
    @extend_schema(
        operation_id="notifications_push_config_retrieve",
        description=(
            "La llave pública con la que el navegador crea la suscripción de push. Nula si las "
            "push no están configuradas: entonces la app no ofrece activarlas."
        ),
        responses={200: PushConfigSerializer, **error_responses(401)},
    )
    def get(self, request):
        return Response({"public_key": public_key()})


class PushSubscriptionsView(APIView):
    @extend_schema(
        operation_id="notifications_push_subscriptions_create",
        description=(
            "Activa las push en un dispositivo con la suscripción que entrega el navegador. Solo "
            "se aceptan los servicios de push de los navegadores. Repetirla actualiza las llaves "
            "(200); si el dispositivo era de otra cuenta, pasa a esta."
        ),
        request=PushSubscriptionCreateSerializer,
        responses={
            200: PushSubscriptionSerializer,
            201: PushSubscriptionSerializer,
            **error_responses(400, 401, 403),
        },
    )
    def post(self, request):
        data = PushSubscriptionCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        subscription, created = subscribe(request.user, data.validated_data)
        return Response(
            PushSubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PushSubscriptionRemoveView(APIView):
    @extend_schema(
        operation_id="notifications_push_subscriptions_remove",
        description=(
            "Apaga las push en un dispositivo: al desactivarlas y al cerrar sesión. Va por POST "
            "con la dirección en el cuerpo: un DELETE no lleva cuerpo, y en la URL la dirección "
            "quedaría en los registros. 204 también si no existía."
        ),
        request=PushSubscriptionRemoveSerializer,
        responses={204: None, **error_responses(400, 401, 403)},
    )
    def post(self, request):
        data = PushSubscriptionRemoveSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        unsubscribe(request.user, data.validated_data["endpoint"])
        return Response(status=status.HTTP_204_NO_CONTENT)
