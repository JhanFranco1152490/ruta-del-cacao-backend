from common.territorial import InvalidMunicipalityCode as TerritorialInvalidMunicipalityCode
from common.territorial import get_municipality

InvalidMunicipalityCode = TerritorialInvalidMunicipalityCode

NORTE_DE_SANTANDER_CODES = frozenset(
    {
        "54001",
        "54003",
        "54051",
        "54099",
        "54109",
        "54125",
        "54128",
        "54172",
        "54174",
        "54206",
        "54223",
        "54239",
        "54245",
        "54250",
        "54261",
        "54313",
        "54344",
        "54347",
        "54377",
        "54385",
        "54398",
        "54405",
        "54418",
        "54480",
        "54498",
        "54518",
        "54520",
        "54553",
        "54599",
        "54660",
        "54670",
        "54673",
        "54680",
        "54720",
        "54743",
        "54800",
        "54810",
        "54820",
        "54871",
        "54874",
    }
)


def validate_municipality_code(value: str) -> str:
    return get_municipality(value).code
