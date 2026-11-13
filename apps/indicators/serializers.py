from rest_framework import serializers

from apps.common.serializers import FarmProducerSerializer, PeriodQuerySerializer

# Los kg y los kg por hectárea con un decimal, y el área con dos, como en la parcela. Sin
# docstrings en las clases: drf-spectacular los publicaría como descripción del componente.


def _kg(**kwargs):
    return serializers.DecimalField(max_digits=14, decimal_places=1, **kwargs)


def _hectares():
    return serializers.DecimalField(max_digits=12, decimal_places=2)


def _share():
    return serializers.DecimalField(max_digits=4, decimal_places=1, allow_null=True)


class ProducerIndicatorsQuerySerializer(PeriodQuerySerializer):
    max_days = 366

    def extra_fields(self):
        return {
            "farm": serializers.UUIDField(required=False),
            # Solo lo usa la cuenta técnica; para las demás se ignora, como en las listas.
            "producer": serializers.UUIDField(required=False),
        }


class IndicatorPeriodSerializer(serializers.Serializer):
    def get_fields(self):
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        return {"from": serializers.DateField(), "to": serializers.DateField()}


class PlotProductionSerializer(serializers.Serializer):
    plot_id = serializers.UUIDField()
    plot_code = serializers.CharField()
    plot_name = serializers.CharField(allow_blank=True)
    farm_id = serializers.UUIDField()
    farm_code = serializers.CharField()
    farm_name = serializers.CharField()
    is_active = serializers.BooleanField()
    area_hectares = _hectares()
    green_kg = _kg()
    dry_kg = _kg()
    green_kg_per_hectare = _kg(allow_null=True)
    dry_kg_per_hectare = _kg(allow_null=True)


class ProductionMonthSerializer(serializers.Serializer):
    month = serializers.CharField()
    green_kg = _kg()
    dry_kg = _kg()


class ProducerProductionSerializer(serializers.Serializer):
    green_kg = _kg()
    dry_kg = _kg()
    green_kg_not_dried = _kg()
    area_hectares = _hectares()
    green_kg_per_hectare = _kg(allow_null=True)
    dry_kg_per_hectare = _kg(allow_null=True)
    plots = PlotProductionSerializer(many=True)
    months = ProductionMonthSerializer(many=True)


class QualitySplitSerializer(serializers.Serializer):
    classified_kg = _kg()
    g1_kg = _kg()
    g2_kg = _kg()
    discard_kg = _kg()
    g1_pct = _share()
    g2_pct = _share()
    discard_pct = _share()


class ProducerQualitySerializer(QualitySplitSerializer):
    lots_classified = serializers.IntegerField()
    lots_discarded = serializers.IntegerField()


class FarmStockSerializer(serializers.Serializer):
    farm_id = serializers.UUIDField()
    farm_code = serializers.CharField()
    farm_name = serializers.CharField()
    g1_kg = _kg()
    g2_kg = _kg()


class ProducerInventorySerializer(serializers.Serializer):
    g1_kg = _kg()
    g2_kg = _kg()
    total_kg = _kg()
    farms = FarmStockSerializer(many=True)


class SalesMonthSerializer(serializers.Serializer):
    month = serializers.CharField()
    sold_kg = _kg()


class ProducerSalesSerializer(serializers.Serializer):
    sold_kg = _kg()
    g1_kg = _kg()
    g2_kg = _kg()
    sales = serializers.IntegerField()
    months = SalesMonthSerializer(many=True)


class ProducerIndicatorsSerializer(serializers.Serializer):
    period = IndicatorPeriodSerializer()
    production = ProducerProductionSerializer()
    quality = ProducerQualitySerializer()
    inventory = ProducerInventorySerializer()
    sales = ProducerSalesSerializer()


class AssociationIndicatorsQuerySerializer(PeriodQuerySerializer):
    max_days = 366


class AssociationTotalsSerializer(QualitySplitSerializer):
    producers = serializers.IntegerField()
    farms = serializers.IntegerField()
    green_kg = _kg()
    dry_kg = _kg()
    sold_kg = _kg()


class AssociationMonthSerializer(serializers.Serializer):
    month = serializers.CharField()
    green_kg = _kg()
    dry_kg = _kg()
    sold_kg = _kg()


class AssociationFarmSerializer(QualitySplitSerializer):
    farm_id = serializers.UUIDField()
    farm_code = serializers.CharField()
    farm_name = serializers.CharField()
    municipality_code = serializers.CharField()
    producer = FarmProducerSerializer()
    green_kg = _kg()
    dry_kg = _kg()
    sold_kg = _kg()


class AssociationIndicatorsSerializer(serializers.Serializer):
    period = IndicatorPeriodSerializer()
    totals = AssociationTotalsSerializer()
    months = AssociationMonthSerializer(many=True)
    farms = AssociationFarmSerializer(many=True)
