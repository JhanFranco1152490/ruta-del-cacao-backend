from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .municipalities import list_municipalities
from .serializers import MunicipalityListSerializer


class MunicipalityListView(APIView):
    # Son datos públicos de división territorial: basta con tener sesión.
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(MunicipalityListSerializer({"results": list_municipalities()}).data)
