from rest_framework import serializers


class MunicipalitySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class MunicipalityListSerializer(serializers.Serializer):
    results = MunicipalitySerializer(many=True)
