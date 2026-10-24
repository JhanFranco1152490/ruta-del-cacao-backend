"""Los parámetros de secado del productor de demostración, guardados por su servicio con su
historial."""

from dataclasses import asdict

from apps.accounts.models import User
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.models import PostharvestParameters
from apps.postharvest_parameters.services.save import save_parameters

from .catalog import DEMO_DRYING_PARAMETERS


def seed_drying_parameters(owner: User) -> list[str]:
    """Los deja personalizados si no tiene ninguno guardado: nunca los cambió, o se restablecieron
    en un ensayo de la demostración y hay que dejarlos listos otra vez. Si ya tiene, no se tocan:
    pueden ser cambios hechos desde la aplicación."""
    if PostharvestParameters.objects.filter(pk=owner.producer_id).exists():
        return []
    save_parameters(owner, None, 0, {**asdict(DRYING_BASELINE), **DEMO_DRYING_PARAMETERS})
    return ["Parámetros de secado personalizados"]
