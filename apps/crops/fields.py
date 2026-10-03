import re
from datetime import date

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

# `[0-9]` y `\Z`, no `\d` ni `$`: `\d` acepta dígitos de otros alfabetos y `$` un salto de línea
# final.
MONTH_PATTERN = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])\Z")
EARLIEST_PLANTING = date(1950, 1, 1)


@extend_schema_field(
    {"type": "string", "pattern": r"^[0-9]{4}-(0[1-9]|1[0-2])$", "example": "2021-03"}
)
class PlantingMonthField(serializers.Field):
    """El mes de la siembra como `AAAA-MM`; se guarda en el día 1 de ese mes.

    Se guarda la fecha y no la edad porque una edad escrita queda vieja al año siguiente. Un
    cultivo sembrado este mes tiene edad cero y es válido.
    """

    default_error_messages = {
        "invalid": "Escribe el mes de siembra como AAAA-MM.",
        "future": "La fecha de siembra no puede ser posterior al mes actual.",
        "too_old": "La fecha de siembra no puede ser anterior a 1950.",
    }

    def to_internal_value(self, data):
        if not isinstance(data, str) or not MONTH_PATTERN.match(data):
            self.fail("invalid")
        year, month = (int(part) for part in data.split("-"))
        planted = date(year, month, 1)
        if planted < EARLIEST_PLANTING:
            self.fail("too_old")
        if planted > timezone.localdate().replace(day=1):
            self.fail("future")
        return planted

    def to_representation(self, value):
        return value.strftime("%Y-%m")
