from django.core.exceptions import ValidationError

from .territorial import MUNICIPALITIES_BY_CODE, get_department
from .text import fold


def list_municipalities():
    # Cada municipio trae su departamento para que el cliente arme los selectores dependientes
    # (departamento y luego municipio) con una sola petición.
    return [
        {
            "code": municipality.code,
            "name": municipality.name,
            "department": {
                "code": municipality.department_code,
                "name": get_department(municipality.department_code).name,
            },
        }
        for municipality in sorted(
            MUNICIPALITIES_BY_CODE.values(), key=lambda item: fold(item.name)
        )
    ]


def municipality_codes_matching(term: str) -> list[str]:
    folded = fold(term)
    return [
        municipality.code
        for municipality in MUNICIPALITIES_BY_CODE.values()
        if folded in fold(municipality.name)
    ]


def validate_municipality_code(value: str) -> None:
    if value not in MUNICIPALITIES_BY_CODE:
        raise ValidationError("El municipio no pertenece a Norte de Santander.")
