from rest_framework import serializers

from apps.common.territorial import InvalidMunicipalityCode, get_municipality


class FarmFilterSerializer(serializers.Serializer):
    # Query params compartidos por el listado y el mapa: así los dos muestran siempre lo mismo.
    search = serializers.CharField(required=False, allow_blank=True)
    producer = serializers.UUIDField(required=False)
    municipality = serializers.CharField(required=False)

    def validate_municipality(self, value):
        try:
            return get_municipality(value).code
        except InvalidMunicipalityCode:
            raise serializers.ValidationError("El municipio no está en el catálogo.") from None


def validated_filters(query_params) -> dict:
    serializer = FarmFilterSerializer(data=query_params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)
