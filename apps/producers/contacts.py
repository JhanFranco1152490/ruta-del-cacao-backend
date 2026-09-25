import re

_PHONE_FORMAT = re.compile(r"^\d{7,10}$")


class InvalidPhoneNumber(ValueError):
    pass


def normalize_phone(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if not _PHONE_FORMAT.fullmatch(normalized):
        raise InvalidPhoneNumber("El telefono debe contener solo entre 7 y 10 digitos.")

    return normalized
