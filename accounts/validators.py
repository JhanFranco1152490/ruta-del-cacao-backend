from django.core.exceptions import ValidationError


def normalize_document(value):
    return "".join(value.strip().upper().split()).replace(".", "").replace("-", "")


def validate_document_number(document_type, value):
    normalized = normalize_document(value)
    if not normalized or not normalized.isdigit():
        raise ValidationError("El número de documento debe contener solo dígitos.")
    if len(normalized) > 15:
        raise ValidationError("El número de documento debe tener máximo 15 dígitos.")
    return normalized


class MaximumLengthValidator:
    def validate(self, password, user=None):
        if len(password) > 50:
            raise ValidationError(self.get_help_text(), code="password_too_long")

    def get_help_text(self):
        return "La contraseña debe tener como máximo 50 caracteres."
