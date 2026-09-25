from rest_framework import serializers


class RejectUnknownFieldsMixin:
    """Rechaza los campos que el cliente no puede escribir, en vez de ignorarlos.

    Un campo mal escrito o de solo lectura en el cuerpo se reporta como error de validación
    y no termina en un guardado que parece exitoso pero no cambió lo pedido.
    """

    def to_internal_value(self, data):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = sorted(set(data) - writable) if hasattr(data, "keys") else []
        if unknown:
            raise serializers.ValidationError({name: ["Campo no permitido."] for name in unknown})
        return super().to_internal_value(data)


class MunicipalitySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class MunicipalityListSerializer(serializers.Serializer):
    results = MunicipalitySerializer(many=True)
