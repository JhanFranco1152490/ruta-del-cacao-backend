import sys

from django.http import JsonResponse
from django.views import defaults
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import (
    INTERNAL_ERROR_CODE,
    INTERNAL_ERROR_DETAIL,
    NOT_FOUND_CODE,
    NOT_FOUND_DETAIL,
    error_body,
    log_unhandled_error,
)
from .municipalities import list_municipalities
from .paths import is_api_request
from .schema import error_responses
from .serializers import MunicipalityListSerializer


class MunicipalityListView(APIView):
    # Son datos públicos de división territorial: basta con tener sesión.
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MunicipalityListSerializer, **error_responses(401)})
    def get(self, request):
        return Response(MunicipalityListSerializer({"results": list_municipalities()}).data)


def not_found(request, exception=None):
    # Una ruta que no resuelve nunca llega a DRF, así que su manejador de errores no aplica:
    # sin esto, bajo /api/ el cliente recibiría la página HTML de Django.
    if is_api_request(request):
        return JsonResponse(error_body(str(NOT_FOUND_DETAIL), NOT_FOUND_CODE), status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    # Un fallo fuera de DRF (un middleware, por ejemplo) también debe respetar la forma
    # estándar. Django llama a esta vista mientras atiende la excepción, pero sin configuración
    # de logging propia no la registra con DEBUG=False (su consola solo escribe con DEBUG y no
    # hay ADMINS): se registra aquí igual que en el manejador de la API.
    error = sys.exception()
    if error is not None:
        log_unhandled_error(error)
    if is_api_request(request):
        return JsonResponse(error_body(INTERNAL_ERROR_DETAIL, INTERNAL_ERROR_CODE), status=500)
    return defaults.server_error(request)
