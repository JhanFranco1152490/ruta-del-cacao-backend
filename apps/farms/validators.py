from django.core.exceptions import ValidationError

# Se reexportan porque las migraciones ya aplicadas de fincas los importan desde aquí.
from apps.common.validators import (  # noqa: F401
    validate_latitude,
    validate_longitude,
    validate_positive_area,
)


def validate_altitude(value: int) -> None:
    if not -500 <= value <= 9000:
        raise ValidationError("La altitud debe estar entre -500 y 9000 msnm.")
