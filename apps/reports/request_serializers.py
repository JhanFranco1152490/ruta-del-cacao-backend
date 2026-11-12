from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.municipalities import validate_municipality_code
from apps.common.serializers import PeriodQuerySerializer

from .types import ASSOCIATION_TYPES, FILE_FORMATS, PRODUCER_TYPES, WITHOUT_PERIOD


class ReportQuerySerializer(PeriodQuerySerializer):
    # Un año completo con su día de cierre, como los paneles de indicadores.
    max_days = 366
    types: tuple[str, ...] = ()

    def get_fields(self):
        fields = super().get_fields()
        # El periodo se exige en `validate`: el inventario no lo lleva.
        fields["from"] = serializers.DateField(required=False)
        fields["to"] = serializers.DateField(required=False)
        fields["type"] = serializers.ChoiceField(choices=self.types)
        return fields

    def validate(self, attrs):
        if attrs["type"] in WITHOUT_PERIOD:
            attrs.pop("from", None)
            attrs.pop("to", None)
            return attrs
        missing = [name for name in ("from", "to") if name not in attrs]
        if missing:
            required = self.fields["from"].error_messages["required"]
            raise serializers.ValidationError({name: [required] for name in missing})
        return super().validate(attrs)


class ProducerReportQuerySerializer(ReportQuerySerializer):
    types = PRODUCER_TYPES

    def extra_fields(self):
        return {
            "farm": serializers.UUIDField(required=False),
            "plot": serializers.UUIDField(required=False),
            "lot": serializers.UUIDField(required=False),
            # Solo lo usa la cuenta técnica; para las demás se ignora, como en las listas.
            "producer": serializers.UUIDField(required=False),
        }


class AssociationReportQuerySerializer(ReportQuerySerializer):
    types = ASSOCIATION_TYPES

    def extra_fields(self):
        return {
            "municipality": serializers.CharField(
                required=False, validators=[_municipality_in_catalog]
            ),
            "producer": serializers.UUIDField(required=False),
            "farm": serializers.UUIDField(required=False),
        }


class ExportFileMixin:
    """La misma consulta del reporte, más el formato del archivo."""

    def get_fields(self):
        fields = super().get_fields()
        fields["file"] = serializers.ChoiceField(choices=FILE_FORMATS)
        return fields


class ProducerReportExportQuerySerializer(ExportFileMixin, ProducerReportQuerySerializer):
    pass


class AssociationReportExportQuerySerializer(ExportFileMixin, AssociationReportQuerySerializer):
    pass


def _municipality_in_catalog(value):
    try:
        validate_municipality_code(value)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from None
