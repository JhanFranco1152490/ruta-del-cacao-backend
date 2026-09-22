import re

from django.core.exceptions import ValidationError


def normalize_document(value):
    return "".join(value.strip().upper().split()).replace(".", "").replace("-", "")


def validate_document_number(document_type, value):
    normalized = normalize_document(value)
    if document_type in {"CC", "CE", "NIT"} and not normalized.isdigit():
        raise ValidationError("El número de CC, CE o NIT debe contener solo dígitos.")
    if document_type == "PPT" and not re.fullmatch(r"[A-Z0-9]+", normalized):
        raise ValidationError("El número de PPT debe contener letras y dígitos.")
    return normalized


class MaximumLengthValidator:
    def validate(self, password, user=None):
        if len(password) > 50:
            raise ValidationError(self.get_help_text(), code="password_too_long")

    def get_help_text(self):
        return "La contraseña debe tener como máximo 50 caracteres."
