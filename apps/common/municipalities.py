import unicodedata

from django.core.exceptions import ValidationError

from .territorial import MUNICIPALITIES_BY_CODE as TERRITORIAL_MUNICIPALITIES
from .territorial import get_department

MUNICIPALITIES_BY_CODE = {
    code: municipality.name for code, municipality in TERRITORIAL_MUNICIPALITIES.items()
}


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
            TERRITORIAL_MUNICIPALITIES.values(),
            key=lambda item: unicodedata.normalize("NFKD", item.name)
            .encode("ascii", "ignore")
            .decode()
            .casefold(),
        )
    ]


def validate_municipality_code(value: str) -> None:
    if value not in MUNICIPALITIES_BY_CODE:
        raise ValidationError("El municipio no pertenece a Norte de Santander.")
