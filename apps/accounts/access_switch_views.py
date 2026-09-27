from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from .access_switch import get_association_access, set_association_access
from .access_switch_serializers import (
    AssociationAccessSerializer,
    AssociationAccessUpdateSerializer,
)
from .requests import request_id_from


class AssociationAccessView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "accounts.association_access_manage"

    @extend_schema(responses={200: AssociationAccessSerializer, **error_responses(401, 403, 404)})
    def get(self, request):
        return Response(AssociationAccessSerializer(get_association_access(request.user)).data)

    @extend_schema(
        request=AssociationAccessUpdateSerializer,
        responses={200: AssociationAccessSerializer, **error_responses(400, 401, 403, 404)},
    )
    def put(self, request):
        serializer = AssociationAccessUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        access = set_association_access(
            request.user, serializer.validated_data["enabled"], request_id_from(request)
        )
        return Response(AssociationAccessSerializer(access).data)
