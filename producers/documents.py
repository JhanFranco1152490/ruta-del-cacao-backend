import re

DOCUMENT_TYPES = frozenset({"CC", "CE", "PPT", "NIT"})
_SEPARATORS = re.compile(r"[ .-]+")


class InvalidIdentityDocument(ValueError):
    pass


def normalize_document_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in DOCUMENT_TYPES:
        raise InvalidIdentityDocument("Invalid document type.")
    return normalized


def normalize_identity_document(value: str) -> str:
    normalized = _SEPARATORS.sub("", value.strip()).upper()
    if not normalized or not normalized.isalnum():
        raise InvalidIdentityDocument("Invalid identity document.")
    return normalized
