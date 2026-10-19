from django.db import models


class FacilityStatus(models.TextChoices):
    AVAILABLE = "available", "Disponible"
    OCCUPIED = "occupied", "Ocupado"
    INACTIVE = "inactive", "Inactivo"


def facility_status(facility) -> str:
    """El estado de un elemento. No se guarda: sale de sus datos, para que nunca los contradiga.
    Un elemento ocupado siempre está activo (lo exige la base)."""
    if not facility.is_active:
        return FacilityStatus.INACTIVE
    if facility.current_lot_id is not None:
        return FacilityStatus.OCCUPIED
    return FacilityStatus.AVAILABLE
