"""Carga los datos de demostración pasando por los servicios de cada app, con sus mismas reglas
(área disponible, superposición, altitud del municipio, densidad) y su historial.

Es la única app que importa de las demás: arma datos que cruzan todas, igual que `config/` junta
sus rutas. Ninguna app importa de esta.
"""

import math
import uuid
from dataclasses import dataclass

from django.db import transaction
from django.test.utils import override_settings

from apps.accounts.events import record_account_event
from apps.accounts.models import AccountManagementEvent, User
from apps.accounts.system_roles import ADMINISTRATOR, PRODUCER, get_system_role
from apps.crops.models import CacaoVariety
from apps.crops.services import save_characterization
from apps.farms.services import create_farm
from apps.plots.services import create_plot
from apps.producers.models import Producer
from apps.producers.services import change_producer_status, create_producer

from .catalog import (
    DEMO_ADMIN,
    DEMO_PASSWORD,
    DEMO_PRODUCER_EMAIL,
    NORTE_DE_SANTANDER,
    PRODUCERS,
)

METRES_PER_DEGREE_OF_LATITUDE = 110_600

# Registrar un productor le crea su cuenta y programa el correo de activación. Las direcciones de
# demostración no existen: enviarlo solo gastaría la cuota del proveedor de correo y dañaría la
# reputación del remitente con rebotes.
NO_EMAIL = {"default": {"BACKEND": "django.core.mail.backends.dummy.EmailBackend"}}


class MissingVarietyCatalog(Exception):
    """No está el catálogo de variedades: lo carga una migración, falta correr `migrate`."""


@dataclass
class SeedReport:
    producers_created: int = 0
    producers_skipped: int = 0


def seed_demo_data() -> SeedReport:
    """Crea lo que falte y deja las dos cuentas de demostración activas, con su rol y con la
    contraseña publicada. Un productor que ya existe (por su documento) no se toca: puede tener
    cambios hechos desde la aplicación."""
    report = SeedReport()
    # El correo programado sale al confirmar la transacción: por eso ella va dentro del cambio de
    # configuración y no al revés.
    with override_settings(MAILERS=NO_EMAIL), transaction.atomic():
        _restore_account(_demo_admin(), ADMINISTRATOR)
        for definition in PRODUCERS:
            if _producer_exists(definition):
                report.producers_skipped += 1
                continue
            _create_producer_with_records(definition)
            report.producers_created += 1
        _restore_account(User.objects.get(email=DEMO_PRODUCER_EMAIL), PRODUCER)
    return report


def _demo_admin() -> User:
    user = User.objects.filter(email__iexact=DEMO_ADMIN["email"]).first()
    if user is not None:
        return user
    user = User(**DEMO_ADMIN)
    user.set_password(DEMO_PASSWORD)
    user.full_clean()
    user.save()
    user.groups.set([get_system_role(ADMINISTRATOR).group])
    record_account_event(
        AccountManagementEvent.EventType.ACCOUNT_CREATED, uuid.uuid4(), target_user=user
    )
    return user


def _restore_account(user: User, role_code: str) -> None:
    user.is_active = True
    user.set_password(DEMO_PASSWORD)
    user.save(update_fields=["is_active", "password"])
    user.groups.add(get_system_role(role_code).group)


def _producer_exists(definition: dict) -> bool:
    return Producer.objects.filter(
        document_type=definition["document_type"],
        identity_document=definition["identity_document"],
    ).exists()


def _create_producer_with_records(definition: dict) -> None:
    data = {name: value for name, value in definition.items() if name not in ("farms", "status")}
    producer = create_producer(data)
    account = User.objects.get(producer=producer, groups__role__code=PRODUCER)
    for farm_definition in definition["farms"]:
        _create_farm_with_plots(account, farm_definition)
    if definition.get("status") == Producer.Status.INACTIVE:
        change_producer_status(producer.pk, producer.version, Producer.Status.INACTIVE)


def _create_farm_with_plots(actor: User, definition: dict) -> None:
    data = {name: value for name, value in definition.items() if name != "plots"}
    farm, _ = create_farm(actor, {**data, "department_code": NORTE_DE_SANTANDER})
    for plot_definition in definition["plots"]:
        shape = plot_definition["shape"]
        plot, _ = create_plot(
            actor,
            {
                "farm_id": farm.pk,
                "code": plot_definition["code"],
                "area_hectares": plot_definition["area_hectares"],
                "boundary": rectangle(farm, **shape) if shape else None,
            },
        )
        characterization = plot_definition.get("characterization")
        if characterization:
            save_characterization(actor, plot.pk, None, _characterization_data(characterization))


def _characterization_data(definition: dict) -> dict:
    names = {planting["variety"] for planting in definition["plantings"]}
    varieties = dict(CacaoVariety.objects.filter(name__in=names).values_list("name", "pk"))
    if names - varieties.keys():
        raise MissingVarietyCatalog()
    return {
        "management_system": definition["management_system"],
        "shade_type": definition["shade_type"],
        "plantings": [
            {
                **{name: value for name, value in planting.items() if name != "variety"},
                "variety_id": varieties[planting["variety"]],
            }
            for planting in definition["plantings"]
        ],
    }


def rectangle(farm, *, east_m: float, north_m: float, width_m: float, height_m: float):
    """Los cuatro vértices de un rectángulo con centro a `east_m` y `north_m` metros del punto de
    la finca. Los grados se convierten a metros sobre un plano: a la escala de una parcela el
    error es menor que la diferencia que se tolera entre el área declarada y la dibujada."""
    latitude = float(farm.latitude)
    longitude = float(farm.longitude)
    metres_per_degree_of_longitude = METRES_PER_DEGREE_OF_LATITUDE * math.cos(
        math.radians(latitude)
    )
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    return [
        {
            "latitude": latitude + (north_m + dy * height_m / 2) / METRES_PER_DEGREE_OF_LATITUDE,
            "longitude": longitude + (east_m + dx * width_m / 2) / metres_per_degree_of_longitude,
            "source": "map",
        }
        for dx, dy in corners
    ]
