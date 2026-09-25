from apps.common.municipalities import MUNICIPALITIES_BY_CODE


class InvalidMunicipalityCode(ValueError):
    pass


def validate_municipality_code(value: str) -> str:
    code = value.strip()
    if code not in MUNICIPALITIES_BY_CODE:
        raise InvalidMunicipalityCode("El municipio no pertenece a Norte de Santander.")
    return code
