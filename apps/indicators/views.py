from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.contracts.indicators import IndicatorPeriod
from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from .serializers import (
    AssociationIndicatorsQuerySerializer,
    AssociationIndicatorsSerializer,
    ProducerIndicatorsQuerySerializer,
    ProducerIndicatorsSerializer,
)
from .services import association_indicators, producer_indicators


def _period(data) -> IndicatorPeriod:
    return IndicatorPeriod(data["from"], data["to"])


class ProducerIndicatorsView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "indicators.view_producer_indicators"

    @extend_schema(
        description=(
            "El panel de la unidad productiva en el periodo, `from` y `to` incluidos, de hasta "
            "366 días: kg en baba y seco por parcela, por hectárea (con el área declarada) y por "
            "mes; G1, G2 y descarte de lo clasificado o descartado en el periodo; las existencias "
            "de hoy, sin periodo; y los kg vendidos, sin las ventas anuladas. Un empleado ve solo "
            "las fincas que trabaja. `farm` acota a una finca (404 si no la alcanza) y `producer` "
            "solo lo usa la cuenta técnica. Sin divisor, los porcentajes y los kg por hectárea "
            "son nulos."
        ),
        parameters=[ProducerIndicatorsQuerySerializer],
        responses={200: ProducerIndicatorsSerializer, **error_responses(400, 401, 403, 404)},
    )
    def get(self, request):
        query = ProducerIndicatorsQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        indicators = producer_indicators(
            request.user,
            _period(query.validated_data),
            farm_id=query.validated_data.get("farm"),
            producer_id=query.validated_data.get("producer"),
        )
        return Response(ProducerIndicatorsSerializer(indicators).data)


class AssociationIndicatorsView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "indicators.view_association_indicators"

    @extend_schema(
        description=(
            "El panel de la asociación en el periodo, `from` y `to` incluidos, de hasta 366 "
            "días: por finca, los kg en baba y seco, G1, G2 y descarte de lo clasificado o "
            "descartado, y los kg vendidos sin las ventas anuladas, con sus totales y los meses. "
            "Solo las fincas con alguna cifra en el periodo, de la que más produjo a la que "
            "menos. Nada por parcela, por lote ni de existencias."
        ),
        parameters=[AssociationIndicatorsQuerySerializer],
        responses={200: AssociationIndicatorsSerializer, **error_responses(400, 401, 403)},
    )
    def get(self, request):
        query = AssociationIndicatorsQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        indicators = association_indicators(request.user, _period(query.validated_data))
        return Response(AssociationIndicatorsSerializer(indicators).data)
