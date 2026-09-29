from django.core.exceptions import ValidationError


class MaximumLengthValidator:
    def validate(self, password, user=None):
        if len(password) > 50:
            raise ValidationError(self.get_help_text(), code="password_too_long")

    def get_help_text(self):
        return "La contraseña debe tener como máximo 50 caracteres."
