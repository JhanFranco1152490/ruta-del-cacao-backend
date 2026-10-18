from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import HasPermission
from apps.common.schema import error_responses

from ..exceptions import EvidenceTooLarge
from ..serializers import (
    EvidenceListSerializer,
    EvidenceSerializer,
    EvidenceUploadSerializer,
)
from ..services.evidence import (
    MAX_BYTES,
    attach_evidence,
    delete_evidence,
    list_evidence,
    visible_evidence,
)

# Lo que puede ocupar el resto del formulario (el `id` y la hora) además de la foto.
FORM_OVERHEAD = 64 * 1024


class EvidenceView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    # El único endpoint de la API que no recibe JSON: una foto en base64 pesaría un tercio más y
    # se cargaría entera en memoria.
    parser_classes = [MultiPartParser]

    @property
    def required_permission(self):
        if self.request.method == "GET":
            return "activities.view_agriculturalactivity"
        return "activities.complete_agriculturalactivity"

    def initial(self, request, *args, **kwargs):
        # Antes de autenticar: la revisión de CSRF lee el cuerpo, y un cuerpo enorme no debe
        # llegar a escribirse en el disco del servidor.
        if request.method == "POST" and _declared_length(request) > MAX_BYTES + FORM_OVERHEAD:
            raise EvidenceTooLarge()
        super().initial(request, *args, **kwargs)

    @extend_schema(
        operation_id="agricultural_activities_evidence_list",
        description=(
            "Las fotos de un monitoreo o un control, de la primera a la última. Uno que no se ha "
            "realizado no tiene. Otra actividad responde 422 `evidence_not_allowed`."
        ),
        responses={200: EvidenceListSerializer, **error_responses(401, 403, 404, 422)},
    )
    def get(self, request, pk):
        rows = list_evidence(request.user, pk)
        return Response(EvidenceListSerializer({"results": rows}).data)

    @extend_schema(
        operation_id="agricultural_activities_evidence_create",
        description=(
            "Adjunta una foto (JPG o PNG, revisado por el contenido; hasta 5 MB y 5 por "
            "registro) a un monitoreo o a un control realizados, en `multipart/form-data`. La "
            "adjunta quien puede registrar ese monitoreo o control. `id` lo genera el "
            "dispositivo: la misma foto reenviada responde 200; un `id` de otra foto, 400. "
            "Errores propios: 409 `evidence_requires_done` y `evidence_limit_reached`, 413 "
            "`evidence_too_large`, 415 `evidence_format_not_allowed` y 422 "
            "`evidence_not_allowed`."
        ),
        request={"multipart/form-data": EvidenceUploadSerializer},
        responses={
            200: EvidenceSerializer,
            201: EvidenceSerializer,
            **error_responses(400, 401, 403, 404, 409, 413, 415, 422),
        },
    )
    def post(self, request, pk):
        serializer = EvidenceUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        evidence, created = attach_evidence(request.user, pk, serializer.validated_data)
        return Response(
            EvidenceSerializer(evidence).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EvidenceFileView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.view_agriculturalactivity"

    @extend_schema(
        operation_id="evidence_file_retrieve",
        description=(
            "El archivo de una foto, después de revisar que quien la pide alcance su finca. "
            "Nunca hay una dirección pública: 404 si es de otra finca o de otro productor."
        ),
        responses={
            (200, "image/jpeg"): OpenApiTypes.BINARY,
            (200, "image/png"): OpenApiTypes.BINARY,
            **error_responses(401, 403, 404),
        },
    )
    def get(self, request, pk):
        evidence = visible_evidence(request.user, pk)
        response = FileResponse(
            evidence.file.open("rb"),
            content_type=evidence.content_type,
            filename=evidence.file_name,
        )
        # El navegador no adivina otro tipo que el que se revisó al subirla.
        response["X-Content-Type-Options"] = "nosniff"
        return response


class EvidenceDetailView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "activities.complete_agriculturalactivity"

    @extend_schema(
        operation_id="evidence_destroy",
        description=(
            "Elimina una foto equivocada. La elimina quien la subió, quien programa labores en "
            "la finca (el Capataz/Operario o un rol propio con ese permiso) o el Productor (403 "
            "si no); el historial registra quién la eliminó."
        ),
        responses={204: None, **error_responses(401, 403, 404)},
    )
    def delete(self, request, pk):
        delete_evidence(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _declared_length(request) -> int:
    try:
        return int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return 0
