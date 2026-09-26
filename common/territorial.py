"""Versioned territorial reference data for the application domain."""

from dataclasses import dataclass
from types import MappingProxyType


@dataclass(frozen=True)
class Department:
    code: str
    name: str


@dataclass(frozen=True)
class Municipality:
    code: str
    name: str
    department_code: str


class InvalidDepartmentCode(ValueError):
    pass


class InvalidMunicipalityCode(ValueError):
    pass


class MunicipalityDepartmentMismatch(ValueError):
    pass


DEPARTMENTS_BY_CODE = MappingProxyType(
    {
        "54": Department(code="54", name="Norte de Santander"),
    }
)

MUNICIPALITIES_BY_CODE = MappingProxyType(
    {
        "54001": Municipality("54001", "Cúcuta", "54"),
        "54003": Municipality("54003", "Ábrego", "54"),
        "54051": Municipality("54051", "Arboledas", "54"),
        "54099": Municipality("54099", "Bochalema", "54"),
        "54109": Municipality("54109", "Bucarasica", "54"),
        "54125": Municipality("54125", "Cácota", "54"),
        "54128": Municipality("54128", "Cáchira", "54"),
        "54172": Municipality("54172", "Chinácota", "54"),
        "54174": Municipality("54174", "Chitagá", "54"),
        "54206": Municipality("54206", "Convención", "54"),
        "54223": Municipality("54223", "Cucutilla", "54"),
        "54239": Municipality("54239", "Durania", "54"),
        "54245": Municipality("54245", "El Carmen", "54"),
        "54250": Municipality("54250", "El Tarra", "54"),
        "54261": Municipality("54261", "El Zulia", "54"),
        "54313": Municipality("54313", "Gramalote", "54"),
        "54344": Municipality("54344", "Hacarí", "54"),
        "54347": Municipality("54347", "Herrán", "54"),
        "54377": Municipality("54377", "Labateca", "54"),
        "54385": Municipality("54385", "La Esperanza", "54"),
        "54398": Municipality("54398", "La Playa", "54"),
        "54405": Municipality("54405", "Los Patios", "54"),
        "54418": Municipality("54418", "Lourdes", "54"),
        "54480": Municipality("54480", "Mutiscua", "54"),
        "54498": Municipality("54498", "Ocaña", "54"),
        "54518": Municipality("54518", "Pamplona", "54"),
        "54520": Municipality("54520", "Pamplonita", "54"),
        "54553": Municipality("54553", "Puerto Santander", "54"),
        "54599": Municipality("54599", "Ragonvalia", "54"),
        "54660": Municipality("54660", "Salazar", "54"),
        "54670": Municipality("54670", "San Calixto", "54"),
        "54673": Municipality("54673", "San Cayetano", "54"),
        "54680": Municipality("54680", "Santiago", "54"),
        "54720": Municipality("54720", "Sardinata", "54"),
        "54743": Municipality("54743", "Silos", "54"),
        "54800": Municipality("54800", "Teorama", "54"),
        "54810": Municipality("54810", "Tibú", "54"),
        "54820": Municipality("54820", "Toledo", "54"),
        "54871": Municipality("54871", "Villa Caro", "54"),
        "54874": Municipality("54874", "Villa del Rosario", "54"),
    }
)


def get_department(code: str) -> Department:
    try:
        return DEPARTMENTS_BY_CODE[code.strip()]
    except (AttributeError, KeyError) as error:
        raise InvalidDepartmentCode("Invalid department code.") from error


def get_municipality(code: str) -> Municipality:
    try:
        return MUNICIPALITIES_BY_CODE[code.strip()]
    except (AttributeError, KeyError) as error:
        raise InvalidMunicipalityCode("Invalid municipality code.") from error


def validate_municipality_department(municipality_code: str, department_code: str) -> Municipality:
    municipality = get_municipality(municipality_code)
    department = get_department(department_code)
    if municipality.department_code != department.code:
        raise MunicipalityDepartmentMismatch("Municipality does not belong to department.")
    return municipality
