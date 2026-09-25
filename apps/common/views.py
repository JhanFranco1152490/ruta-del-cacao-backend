from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .municipalities import list_municipalities
from .schema import error_responses
from .serializers import MunicipalityListSerializer


class MunicipalityListView(APIView):
    # Son datos públicos de división territorial: basta con tener sesión.
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: MunicipalityListSerializer, **error_responses(401)})
    def get(self, request):
        return Response(MunicipalityListSerializer({"results": list_municipalities()}).data)
