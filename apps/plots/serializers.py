from rest_framework import serializers

from apps.common.serializers import ApiErrorSerializer, RejectUnknownFieldsMixin

from .geometry import ADJUSTED_SOURCE
from .models import Plot

GPS_SOURCE = "gps"
VERTEX_SOURCES = (GPS_SOURCE, "map", ADJUSTED_SOURCE)


class VertexSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7)
    accuracy_m = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    captured_at = serializers.DateTimeField(allow_null=True)
    source = serializers.ChoiceField(choices=VERTEX_SOURCES)


class VertexInputSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    # Sin límite de dígitos: una coordenada fuera de rango debe responder `invalid_boundary`, y
    # eso lo decide la geometría; si el serializer la cortara antes, llegaría como un error
    # genérico de campo. Los decimales de más se redondean a 7 al validar el contorno.
    latitude = serializers.DecimalField(max_digits=None, decimal_places=None)
    longitude = serializers.DecimalField(max_digits=None, decimal_places=None)
    accuracy_m = serializers.DecimalField(
        max_digits=6, decimal_places=1, min_value=0, required=False, allow_null=True, default=None
    )
    captured_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    source = serializers.ChoiceField(choices=VERTEX_SOURCES)

    def validate(self, attrs):
        # `get` y no `[...]`: en una edición parcial DRF no completa los valores por defecto,
        # tampoco en los serializers anidados, así que un campo omitido no llega.
        if attrs.get("accuracy_m") is not None and attrs["source"] != GPS_SOURCE:
            raise serializers.ValidationError(
                {"accuracy_m": ["La precisión solo aplica a un vértice capturado por GPS."]}
            )
        return attrs


class PlotFarmSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class PlotSerializer(serializers.ModelSerializer):
    farm = PlotFarmSerializer()
    boundary = VertexSerializer(many=True, allow_null=True)

    class Meta:
        model = Plot
        fields = [
            "id",
            "farm",
            "code",
            "area_hectares",
            "measured_area_hectares",
            "boundary",
            "version",
            "is_active",
            "captured_at",
            "created_at",
            "updated_at",
        ]
        # Solo de salida: así el esquema los marca como siempre presentes.
        read_only_fields = fields


class PlotWriteSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    code = serializers.CharField(max_length=50)
    area_hectares = serializers.DecimalField(max_digits=10, decimal_places=2)
    # La lista completa de vértices; `null` deja la parcela sin contorno.
    boundary = VertexInputSerializer(many=True, allow_null=True, required=False)


class PlotCreateSerializer(PlotWriteSerializer):
    # Lo genera el dispositivo cuando registra sin conexión; si no llega, lo genera el servidor.
    id = serializers.UUIDField(required=False)
    farm_id = serializers.UUIDField()
    # Hora del dispositivo al capturar; informativa, así que no se valida contra la del servidor.
    captured_at = serializers.DateTimeField(required=False, allow_null=True)


class PlotUpdateSerializer(PlotWriteSerializer):
    code = serializers.CharField(max_length=50, required=False)
    area_hectares = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_active = serializers.BooleanField(required=False)
    expected_version = serializers.IntegerField(min_value=1, write_only=True)

    def validate(self, attrs):
        # Con partial=True ningún campo es obligatorio, ni siquiera la versión.
        if "expected_version" not in attrs:
            raise serializers.ValidationError({"expected_version": ["Este campo es requerido."]})
        if len(attrs) == 1:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class PlotListQuerySerializer(serializers.Serializer):
    farm = serializers.UUIDField(required=False)
    is_active = serializers.BooleanField(required=False)
    search = serializers.CharField(required=False, allow_blank=True)


class OverlapSerializer(serializers.Serializer):
    plot_id = serializers.UUIDField()
    code = serializers.CharField()
    overlap_area_hectares = serializers.DecimalField(max_digits=10, decimal_places=4)
    # El contorno de la vecina, para dibujarla aunque el dispositivo no la tenga guardada.
    boundary = VertexSerializer(many=True)


class PlotRuleErrorSerializer(ApiErrorSerializer):
    # Solo se documenta: el 422 lo arma el manejador global de errores. `measured_area_hectares`
    # llega con `area_mismatch`; `overlaps` y la sugerencia, con `plot_overlap`.
    measured_area_hectares = serializers.DecimalField(
        max_digits=10, decimal_places=4, required=False
    )
    overlaps = OverlapSerializer(many=True, required=False)
    suggested_boundary = VertexSerializer(many=True, allow_null=True, required=False)
    suggested_measured_area_hectares = serializers.DecimalField(
        max_digits=10, decimal_places=4, allow_null=True, required=False
    )


class PlotConflictErrorSerializer(ApiErrorSerializer):
    # Solo se documenta. `current` llega con `stale_version` y con `plot_id_conflict` de una
    # parcela propia, para mostrar la versión del servidor sin otra consulta. Nunca con una
    # parcela de otro productor.
    current = PlotSerializer(required=False)
