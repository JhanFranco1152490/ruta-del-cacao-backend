"""La única vista de lotes que no pide sesión: la trazabilidad pública que abre el QR."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.client_ip import ClientIPThrottle
from apps.common.schema import error_responses

from .public_serializers import PublicLotTraceabilitySerializer
from .services.public import public_lot_traceability

# Lo que cambia después de la clasificación es poco (el ingreso a bodega), y la respuesta no trae
# datos personales: el navegador y un proxy pueden guardarla unos minutos.
PUBLIC_CACHE = "public, max-age=300"


class PublicTraceabilityThrottle(ClientIPThrottle):
    scope = "public_traceability"


class PublicLotTraceabilityView(APIView):
    # Sin autenticación: no lee la cookie de sesión, así que una sesión vencida en el navegador del
    # consumidor no le da un 401, y la respuesta es la misma con o sin cuenta.
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PublicTraceabilityThrottle]

    @extend_schema(
        operation_id="public_lot_traceability",
        description=(
            "La trazabilidad pública del lote que abre su código QR, sin sesión: la finca, el "
            "municipio y la variedad de origen, la fecha de cada etapa y su calidad. Nunca trae "
            "precios, compradores, kilos ni personas. Un token que no existe o no tiene la forma "
            "de uno responde el mismo 404. Límite de consultas por IP (429)."
        ),
        auth=[],
        responses={200: PublicLotTraceabilitySerializer, **error_responses(404, 429)},
    )
    def get(self, request, token):
        data = PublicLotTraceabilitySerializer(public_lot_traceability(token)).data
        return Response(data, headers={"Cache-Control": PUBLIC_CACHE})
