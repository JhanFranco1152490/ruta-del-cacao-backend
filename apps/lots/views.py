from django.urls import reverse
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import ActionPermission
from apps.common.schema import error_responses

from .exceptions import HarvestAlreadyInLot, StaleLotVersion
from .serializers import (
    LotConflictErrorSerializer,
    LotCreateSerializer,
    LotDeleteQuerySerializer,
    LotListQuerySerializer,
    LotSerializer,
    LotSummaryQuerySerializer,
    LotSummarySerializer,
)
from .services.create import create_lot
from .services.delete import delete_lot
from .services.queries import get_lot, list_lots, lot_summary


@extend_schema_view(
    list=extend_schema(
        description=(
            "Los lotes de las fincas que la cuenta alcanza, paginados, del de cosecha más "
            "reciente al más antiguo. `search` busca una parte del código (`261014`, "
            "`F02-P05`), sin distinguir mayúsculas; `from` y `to` son la fecha de la cosecha."
        ),
        parameters=[
            LotListQuerySerializer,
            OpenApiParameter("producer", str, description="Solo para la cuenta técnica."),
        ],
        responses={200: LotSerializer(many=True), **error_responses(400, 401, 403, 404)},
    ),
    retrieve=extend_schema(responses={200: LotSerializer, **error_responses(401, 403, 404)}),
    create=extend_schema(
        description=(
            "Conforma el lote de una cosecha y le asigna su código. Solo en línea: el código lo "
            "asigna el servidor. `id` lo genera el dispositivo: reenviar el mismo `id` para la "
            "misma cosecha responde 200 con el lote ya creado. Una cosecha que ya forma un lote "
            "es 409 `harvest_already_in_lot`, con ese lote en `current`."
        ),
        request=LotCreateSerializer,
        responses={
            200: LotSerializer,
            201: LotSerializer,
            409: LotConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
    destroy=extend_schema(
        description=(
            "Elimina un lote conformado por error. Requiere `expected_version` en la URL. Solo "
            "un lote Generado: en otro estado responde 409 `lot_invalid_status` con el estado "
            "actual. La cosecha queda sin lote y el código no se vuelve a usar."
        ),
        parameters=[
            OpenApiParameter(
                "expected_version",
                int,
                required=True,
                description="La `version` del lote que se leyó.",
            )
        ],
        responses={
            204: None,
            409: LotConflictErrorSerializer,
            **error_responses(400, 401, 403, 404),
        },
    ),
)
class LotViewSet(GenericViewSet):
    serializer_class = LotSerializer
    permission_classes = [IsAuthenticated, ActionPermission]
    action_permissions = {
        "list": "lots.view_lot",
        "retrieve": "lots.view_lot",
        "create": "lots.add_lot",
        "destroy": "lots.delete_lot",
        "summary": "lots.view_lot",
    }
    filter_backends = []
    lookup_value_converter = "uuid"

    def list(self, request):
        query = LotListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        page = self.paginate_queryset(list_lots(request.user, query.validated_data))
        return self.get_paginated_response(LotSerializer(page, many=True).data)

    def retrieve(self, request, pk):
        return Response(LotSerializer(get_lot(request.user, pk)).data)

    def create(self, request):
        serializer = LotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot, created = create_lot(request.user, serializer.validated_data)
        data = LotSerializer(lot).data
        if not created:
            return Response(data)
        return Response(
            data,
            status=status.HTTP_201_CREATED,
            headers={"Location": reverse("lot-detail", args=[lot.pk])},
        )

    def destroy(self, request, pk):
        # La versión va en la URL: un cuerpo en DELETE no tiene significado definido en HTTP y
        # algunos intermediarios lo descartan.
        query = LotDeleteQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        delete_lot(request.user, pk, query.validated_data["expected_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        description=(
            "Cuántos lotes y cuántos kilos en verde hay en cada estado, con los mismos filtros de "
            "la lista menos `status`: el recuento sirve para elegirlo. Trae todos los estados de "
            "la cadena, en orden, también los que tienen cero."
        ),
        parameters=[
            LotSummaryQuerySerializer,
            OpenApiParameter("producer", str, description="Solo para la cuenta técnica."),
        ],
        responses={200: LotSummarySerializer, **error_responses(400, 401, 403)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def summary(self, request):
        query = LotSummaryQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        totals = lot_summary(request.user, query.validated_data)
        return Response(LotSummarySerializer({"results": totals}).data)

    def handle_exception(self, exc):
        # El servicio lanza el conflicto con el lote del dominio; aquí se convierte en lo que el
        # cliente necesita para mostrar el vigente sin otra consulta.
        if isinstance(exc, HarvestAlreadyInLot):
            exc.extra = {"current": LotSerializer(exc.current_lot).data}
        elif isinstance(exc, StaleLotVersion):
            exc.extra = {"current": LotSerializer(exc.current_lot).data}
        return super().handle_exception(exc)
