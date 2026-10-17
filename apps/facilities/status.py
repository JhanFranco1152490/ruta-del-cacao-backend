from django.db import models


class FacilityStatus(models.TextChoices):
    AVAILABLE = "available", "Disponible"
    INACTIVE = "inactive", "Inactivo"


def facility_status(facility) -> str:
    """El estado de un elemento. No se guarda: sale de sus datos, para que nunca los contradiga."""
    if not facility.is_active:
        return FacilityStatus.INACTIVE
    return FacilityStatus.AVAILABLE
