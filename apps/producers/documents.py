import re

DOCUMENT_TYPES = frozenset({"CC", "CE", "PPT", "NIT"})
IDENTITY_DOCUMENT_PATTERN = re.compile(r"^[0-9]{6,15}$")


class InvalidIdentityDocument(ValueError):
    pass


def normalize_document_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in DOCUMENT_TYPES:
        raise InvalidIdentityDocument("Invalid document type.")
    return normalized


def normalize_identity_document(value: str) -> str:
    normalized = value.strip()
    if not IDENTITY_DOCUMENT_PATTERN.fullmatch(normalized):
        raise InvalidIdentityDocument(
            "El número de documento debe contener solo dígitos, entre 6 y 15 caracteres."
        )
    return normalized
