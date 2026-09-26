import re

from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils import timezone

_DOCUMENT_SEPARATORS = re.compile(r"[\s.\-]")


def strip_document_separators(value: str) -> str:
    """Quita espacios, puntos y guiones de un documento escrito a mano (1.090-123 → 1090123)."""
    return _DOCUMENT_SEPARATORS.sub("", value).upper()


validate_document_digits = RegexValidator(
    r"^[0-9]{1,15}\Z", "El número de documento debe contener solo dígitos, máximo 15."
)

validate_producer_document = RegexValidator(
    r"^[0-9]{6,15}\Z", "El número de documento debe contener solo dígitos, entre 6 y 15."
)

validate_phone = RegexValidator(
    r"^[0-9]{7,10}\Z", "El teléfono debe contener solo entre 7 y 10 dígitos."
)


def validate_not_future(value):
    if value > timezone.localdate():
        raise ValidationError("La fecha no puede ser futura.")
