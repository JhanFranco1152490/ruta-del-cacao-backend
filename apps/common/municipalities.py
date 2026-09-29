import unicodedata

from django.core.exceptions import ValidationError

from .territorial import MUNICIPALITIES_BY_CODE as TERRITORIAL_MUNICIPALITIES

MUNICIPALITIES_BY_CODE = {
    code: municipality.name for code, municipality in TERRITORIAL_MUNICIPALITIES.items()
}


def list_municipalities():
    return [
        {"code": code, "name": name}
        for code, name in sorted(
            MUNICIPALITIES_BY_CODE.items(),
            key=lambda item: unicodedata.normalize("NFKD", item[1])
            .encode("ascii", "ignore")
            .decode()
            .casefold(),
        )
    ]


def validate_municipality_code(value: str) -> None:
    if value not in MUNICIPALITIES_BY_CODE:
        raise ValidationError("El municipio no pertenece a Norte de Santander.")
