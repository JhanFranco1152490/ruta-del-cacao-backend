from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.views import enforce_csrf

from .catalogs import list_municipalities
from .errors import producer_error, validation_error
from .exceptions import DuplicateDocumentError, ProducerValidationError
from .listing import list_producers
from .operations import create_producer
from .permissions import (
    CanAccessMunicipalityCatalog,
    CanChangeProducerStatus,
    CanCreateProducers,
    CanUpdateProducers,
    CanViewProducers,
)
from .serializers import (
    ProducerCreateSerializer,
    ProducerListQuerySerializer,
    ProducerStatusSerializer,
    ProducerUpdateSerializer,
)
from .status import activate_producer, deactivate_producer
from .updates import (
    ProducerNotFoundError,
    StaleVersionError,
    update_producer,
)


def serialize_producer(producer):
    return {
        "id": str(producer.id),
        "member_code": producer.member_code,
        "document_type": producer.document_type,
        "identity_document": producer.identity_document,
        "first_name": producer.first_name,
        "last_name": producer.last_name,
        "phone": producer.phone,
        "email": producer.email,
        "municipality_code": producer.municipality_code,
        "joined_on": producer.joined_on,
        "status": producer.status,
        "version": producer.version,
        "created_at": producer.created_at,
        "updated_at": producer.updated_at,
    }


def serialize_producer_list_item(producer):
    return {
        "id": str(producer.id),
        "member_code": producer.member_code,
        "document_type": producer.document_type,
        "identity_document": producer.identity_document,
        "first_name": producer.first_name,
        "last_name": producer.last_name,
        "municipality_code": producer.municipality_code,
        "status": producer.status,
    }


class PrivateProducerAPIView(APIView):
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class ProducerListCreateView(PrivateProducerAPIView):
    def get_permissions(self):
        return [CanViewProducers()] if self.request.method == "GET" else [CanCreateProducers()]

    def get(self, request):
        serializer = ProducerListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        result = list_producers(serializer.validated_data)
        result["results"] = [serialize_producer_list_item(item) for item in result["results"]]
        return Response(result)

    def post(self, request):
        enforce_csrf(request)
        serializer = ProducerCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        try:
            producer = create_producer(serializer.validated_data)
        except ProducerValidationError as error:
            return validation_error(error.errors)
        except DuplicateDocumentError:
            return producer_error(
                "duplicate_document", "El documento ya se encuentra registrado.", status=409
            )
        return Response(
            serialize_producer(producer),
            status=status.HTTP_201_CREATED,
            headers={"Location": f"/api/producers/{producer.id}"},
        )


class ProducerDetailView(PrivateProducerAPIView):
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
            return Response(
                serialize_producer(
                    update_producer(producer_id, expected_version, serializer.validated_data)
                )
            )
        except ProducerValidationError as error:
            return validation_error(error.errors)
        except ProducerNotFoundError:
            return producer_error("not_found", "El productor no existe.", status=404)
        except StaleVersionError:
            return producer_error("stale_version", "La ficha fue modificada.", status=409)
        except DuplicateDocumentError:
            return producer_error(
                "duplicate_document", "El documento ya se encuentra registrado.", status=409
            )


class ProducerStatusView(PrivateProducerAPIView):
    permission_classes = [CanChangeProducerStatus]

    def patch(self, request, producer_id):
        enforce_csrf(request)
        serializer = ProducerStatusSerializer(data=request.data)
        if not serializer.is_valid():
            return validation_error(serializer.errors)
        requested_status = serializer.validated_data["status"]
        change_status = activate_producer if requested_status == "active" else deactivate_producer
        try:
            return Response(
                serialize_producer(
                    change_status(producer_id, serializer.validated_data["expected_version"])
                )
            )
        except ProducerNotFoundError:
            return producer_error("not_found", "El productor no existe.", status=404)
        except StaleVersionError:
            return producer_error("stale_version", "La ficha fue modificada.", status=409)


class MunicipalityCatalogView(APIView):
    permission_classes = [CanAccessMunicipalityCatalog]

    def get(self, request):
        return Response({"results": list_municipalities()})
