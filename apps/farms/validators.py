from django.core.exceptions import ValidationError

from apps.common.municipality_altitude import altitude_range_for
from apps.common.territorial import get_municipality

# Se reexportan porque las migraciones ya aplicadas de fincas los importan desde aquí.
from apps.common.validators import (  # noqa: F401
    validate_latitude,
    validate_longitude,
    validate_positive_area,
)


def validate_altitude(value: int) -> None:
    if not -500 <= value <= 9000:
        raise ValidationError("La altitud debe estar entre -500 y 9000 msnm.")


def validate_altitude_for_municipality(altitude_masl: int, municipality_code: str) -> None:
    """La altitud tiene que caber en el terreno del municipio de la finca. Se exige al crear y
    cuando cambia la altitud o el municipio, no en cada edición: una finca guardada antes de la
    regla debe poder seguir desactivándose o corrigiendo sus otros datos."""
    terrain = altitude_range_for(municipality_code)
    if terrain is None or terrain[0] <= altitude_masl <= terrain[1]:
        return
    name = get_municipality(municipality_code).name
    raise ValidationError(
        {
            "altitude_masl": [
                f"La altitud no corresponde a {name}: el terreno del municipio va de "
                f"{terrain[0]} a {terrain[1]} m."
            ]
        }
    )
