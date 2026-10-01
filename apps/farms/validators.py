import unicodedata
from decimal import Decimal

from django.core.exceptions import ValidationError


def normalize_farm_name(value: str) -> str:
    return unicodedata.normalize("NFKC", value.strip()).casefold()


def validate_positive_area(value: Decimal) -> None:
    if value <= 0:
        raise ValidationError("El área debe ser mayor a 0.")


def validate_altitude(value: int) -> None:
    if not -500 <= value <= 9000:
        raise ValidationError("La altitud debe estar entre -500 y 9000 msnm.")


def validate_latitude(value: Decimal) -> None:
    if not -90 <= value <= 90:
        raise ValidationError("La latitud debe estar entre -90 y 90.")


def validate_longitude(value: Decimal) -> None:
    if not -180 <= value <= 180:
        raise ValidationError("La longitud debe estar entre -180 y 180.")
