from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.common.serializers import PeriodQuerySerializer, full_name

from .models import Grade, Sale

ONE_DECIMAL = 1


def _kilos():
    return serializers.DecimalField(max_digits=9, decimal_places=ONE_DECIMAL)


class SaleFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class SaleBuyerSerializer(serializers.Serializer):
    # Con su nombre actual: la venta apunta al comprador y no copia sus datos.
    id = serializers.UUIDField()
    name = serializers.CharField()
    buyer_type = serializers.CharField()
    is_active = serializers.BooleanField()


class SalePersonSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.SerializerMethodField()

    def get_full_name(self, account) -> str:
        return full_name(account)


class SaleLotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()


class SaleLineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    lot = SaleLotSerializer()
    grade = serializers.ChoiceField(choices=Grade.choices)
    quantity_kg = _kilos()
    price_per_kg = serializers.IntegerField()
    subtotal = serializers.IntegerField()


class SaleInvoiceSerializer(serializers.Serializer):
    file_name = serializers.CharField(source="invoice_name")
    content_type = serializers.CharField(source="invoice_content_type")
    size = serializers.IntegerField(source="invoice_size")
    uploaded_at = serializers.DateTimeField(source="invoice_uploaded_at")


class SaleVoidSerializer(serializers.Serializer):
    voided_at = serializers.DateTimeField()
    voided_by = SalePersonSerializer()
    reason = serializers.CharField(source="void_reason")


# Una venta como la muestra la lista: sin sus líneas, con sus kilos y su total.
class SaleListItemSerializer(serializers.Serializer):

    id = serializers.UUIDField()
    code = serializers.CharField()
    farm = SaleFarmSerializer()
    buyer = SaleBuyerSerializer()
    sale_date = serializers.DateField()
    notes = serializers.CharField()
    # Los kilos y el total los calcula la consulta, en la misma lectura.
    g1_kg = _kilos()
    g2_kg = _kilos()
    total = serializers.IntegerField()
    invoice = serializers.SerializerMethodField()
    status = serializers.ChoiceField(choices=Sale.Status.choices)
    created_at = serializers.DateTimeField()
    created_by = SalePersonSerializer()
    voided = serializers.SerializerMethodField()
    version = serializers.IntegerField()

    # Los datos del soporte y de la anulación son campos de la venta: sin ellos, `null`.
    @extend_schema_field(SaleInvoiceSerializer(allow_null=True))
    def get_invoice(self, sale):
        return SaleInvoiceSerializer(sale).data if sale.invoice else None

    @extend_schema_field(SaleVoidSerializer(allow_null=True))
    def get_voided(self, sale):
        return SaleVoidSerializer(sale).data if sale.voided_at else None


# La ficha de una venta, con sus líneas.
class SaleSerializer(SaleListItemSerializer):

    lines = SaleLineSerializer(many=True)


class SaleListQuerySerializer(PeriodQuerySerializer):
    # Un año como mucho: la lista se pide por mes, y un año deja ver una temporada completa.
    max_days = 366

    def extra_fields(self):
        return {
            "farm": serializers.UUIDField(required=False),
            "buyer": serializers.UUIDField(required=False),
            "status": serializers.ChoiceField(choices=Sale.Status.choices, required=False),
            "search": serializers.CharField(required=False, allow_blank=True, max_length=20),
            "producer": serializers.UUIDField(required=False),
        }


class SaleSummaryQuerySerializer(SaleListQuerySerializer):
    # Solo cuenta las registradas: el estado no es un filtro del resumen.
    def extra_fields(self):
        fields = super().extra_fields()
        fields.pop("status")
        return fields


class SaleSummarySerializer(serializers.Serializer):
    total = serializers.IntegerField()
    g1_kg = _kilos()
    g2_kg = _kilos()
    sales = serializers.IntegerField()
