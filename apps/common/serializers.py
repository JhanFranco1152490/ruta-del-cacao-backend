from rest_framework import serializers


# Un comentario y no un docstring: el esquema OpenAPI toma el docstring de la clase como
# descripción del componente y publicaría este texto interno en los tipos del cliente.
class RejectUnknownFieldsMixin:
    # Rechaza los campos que el cliente no puede escribir, en vez de ignorarlos: un campo mal
    # escrito o de solo lectura en el cuerpo se reporta como error de validación y no termina
    # en un guardado que parece exitoso pero no cambió lo pedido.

    def to_internal_value(self, data):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unknown = sorted(set(data) - writable) if hasattr(data, "keys") else []
        if unknown:
            raise serializers.ValidationError({name: ["Campo no permitido."] for name in unknown})
        return super().to_internal_value(data)


class RequireSomeFieldMixin:
    # Un PATCH sin ningún campo no cambia nada: se rechaza en vez de responder éxito.

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class RequireVersionedChangeMixin:
    # Un PATCH versionado necesita `expected_version` (el bloqueo optimista) y al menos un campo
    # más que cambiar. Con `partial=True` ningún campo es obligatorio, ni siquiera la versión,
    # así que se exige aquí. No encadena a la validación del serializer de creación (p. ej. la
    # ubicación obligatoria de una finca): en un PATCH lo que no llega se queda como está.

    def validate(self, attrs):
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class DepartmentSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class MunicipalitySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    department = DepartmentSerializer()


class MunicipalityListSerializer(serializers.Serializer):
    results = MunicipalitySerializer(many=True)


def full_name(account) -> str:
    """El nombre con que se muestra una cuenta; sin nombre, su correo: es la única forma de
    reconocerla."""
    return account.get_full_name() or account.email


# De quién es una finca, como lo muestran las fincas y las parcelas. Conserva el nombre con que
# lo publica el esquema OpenAPI.
class FarmProducerSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    member_code = serializers.CharField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class ApiErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()
    code = serializers.CharField()
    fields = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


class DeviationSerializer(serializers.Serializer):
    # Un desvío de lo que se acaba de guardar, para avisarlo en el momento. `limit` es texto
    # porque en un rango son dos valores (`"7.6-8.5"`).
    kind = serializers.CharField()
    severity = serializers.ChoiceField(choices=["normal", "critical"])
    value = serializers.CharField()
    limit = serializers.CharField()


class PeriodQuerySerializer(serializers.Serializer):
    # Una lista que se pide por periodo, `from` y `to` incluidos, hasta `max_days`: cubre lo que se
    # ve sin abrir la puerta a pedir años enteros sin paginar. Cada lista suma sus filtros en
    # `extra_fields`.
    max_days: int

    def extra_fields(self):
        return {}

    def get_fields(self):
        # `from` es palabra reservada de Python: no puede ser el nombre de un atributo.
        return {
            "from": serializers.DateField(),
            "to": serializers.DateField(),
            **self.extra_fields(),
        }

    def validate(self, attrs):
        if attrs["to"] < attrs["from"]:
            raise serializers.ValidationError({"to": ["Debe ser igual o posterior a `from`."]})
        if (attrs["to"] - attrs["from"]).days + 1 > self.max_days:
            raise serializers.ValidationError(
                {"to": [f"El periodo no puede pasar de {self.max_days} días."]}
            )
        return attrs
