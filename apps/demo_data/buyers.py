"""El Comercializador del productor de demostración y sus compradores, creados por los servicios.

Cada parte revisa si ya está y solo agrega lo que falta: un comprador se busca por su documento,
así que uno que alguien editó desde la aplicación no se vuelve a crear ni se toca.
"""

import uuid

from apps.accounts.models import User
from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.users.creation import create_account
from apps.buyers.models import Buyer
from apps.buyers.services import create_buyer, update_buyer

from .catalog import DEMO_BUYERS, DEMO_SALES_MANAGER


def seed_buyers(owner: User, restore_account) -> list[str]:
    """Deja la cuenta Comercializador y los compradores, y devuelve lo que hizo, una línea por
    parte. `owner` es la cuenta del productor; `restore_account` deja una cuenta activa y con la
    contraseña pública."""
    _sales_manager(owner, restore_account)
    created = 0
    for definition in DEMO_BUYERS:
        if Buyer.objects.filter(
            producer=owner.producer,
            document_type=definition["document_type"],
            identity_document=definition["identity_document"],
        ).exists():
            continue
        data = {key: value for key, value in definition.items() if key != "is_active"}
        buyer = create_buyer(owner, data)
        if not definition.get("is_active", True):
            update_buyer(owner, buyer.pk, buyer.version, {"is_active": False})
        created += 1
    return [f"Compradores: {created}"] if created else []


def _sales_manager(owner: User, restore_account) -> User:
    """Se crea una vez; la contraseña pública se le restablece siempre, como a las demás cuentas de
    demostración."""
    user = User.objects.filter(email__iexact=DEMO_SALES_MANAGER["email"]).first()
    if user is None:
        data = DEMO_SALES_MANAGER | {
            "role_ids": [get_system_role(SALES_MANAGER).pk],
            "all_farms": True,
        }
        user = create_account(owner, data, uuid.uuid4()).user
    restore_account(user, SALES_MANAGER)
    return user
