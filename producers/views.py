from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import producer_error, validation_error
from .listing import list_producers
from .operations import DuplicateDocumentError, create_producer
from .permissions import CanChangeProducerStatus, CanCreateProducers, CanUpdateProducers, CanViewProducers
from .serializers import ProducerCreateSerializer, ProducerListQuerySerializer, ProducerStatusSerializer, ProducerUpdateSerializer
from .status import deactivate_producer
from .updates import (
    DuplicateDocumentError as UpdateDuplicateDocumentError,
    ProducerNotFoundError,
    StaleVersionError,
    update_producer,
)
from accounts.views import enforce_csrf

def serialize_producer(producer):
    return {
        "id": str(producer.id), "member_code": producer.member_code,
        "document_type": producer.document_type, "identity_document": producer.identity_document,
        "first_name": producer.first_name, "last_name": producer.last_name,
        "phone": producer.phone, "email": producer.email,
        "municipality_code": producer.municipality_code, "joined_on": producer.joined_on,
        "status": producer.status, "version": producer.version,
        "created_at": producer.created_at, "updated_at": producer.updated_at,
    }


class ProducerListCreateView(APIView):
    def get_permissions(self):
        return [CanViewProducers()] if self.request.method == "GET" else [CanCreateProducers()]

    def get(self, request):
        serializer = ProducerListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = list_producers(serializer.validated_data)
        result["results"] = [serialize_producer(item) for item in result["results"]]
        return Response(result)

    def post(self, request):
        enforce_csrf(request)
        serializer = ProducerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        try:
            producer = create_producer(serializer.validated_data)
        except DuplicateDocumentError:
            return producer_error("duplicate_document", "El documento ya se encuentra registrado.", status=409)
        return Response(serialize_producer(producer), status=status.HTTP_201_CREATED, headers={"Location": f"/api/producers/{producer.id}"})


class ProducerDetailView(APIView):
    def get_permissions(self):
        return [CanViewProducers()] if self.request.method == "GET" else [CanUpdateProducers()]

    def get(self, request, producer_id):
        from .models import Producer
        try:
            return Response(serialize_producer(Producer.objects.get(pk=producer_id)))
        except Producer.DoesNotExist:
            return producer_error("not_found", "El productor no existe.", status=404)

    def patch(self, request, producer_id):
        enforce_csrf(request)
        serializer = ProducerUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        expected_version = serializer.validated_data.pop("expected_version")
        try:
            return Response(serialize_producer(update_producer(producer_id, expected_version, serializer.validated_data)))
        except ProducerNotFoundError:
            return producer_error("not_found", "El productor no existe.", status=404)
        except StaleVersionError:
            return producer_error("stale_version", "La ficha fue modificada.", status=409)
        except UpdateDuplicateDocumentError:
            return producer_error("duplicate_document", "El documento ya se encuentra registrado.", status=409)


class ProducerStatusView(APIView):
    permission_classes = [CanChangeProducerStatus]

    def patch(self, request, producer_id):
        enforce_csrf(request)
        serializer = ProducerStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        try:
            return Response(serialize_producer(deactivate_producer(producer_id, serializer.validated_data["expected_version"])))
        except ProducerNotFoundError:
            return producer_error("not_found", "El productor no existe.", status=404)
        except StaleVersionError:
            return producer_error("stale_version", "La ficha fue modificada.", status=409)
