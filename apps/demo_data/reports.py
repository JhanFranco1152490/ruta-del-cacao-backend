"""Los reportes del productor para el capataz de La Esperanza: un rol propio que solo le suma el
permiso de reportes. Con lo que ya tiene (cosechas y lotes) genera Producción, Calidad y
Trazabilidad, y Comercialización le dice que no tiene permiso: así se muestra en vivo que cada tipo
pide además el permiso de su módulo.

Se crea por los servicios de cuentas, con la cuenta del productor, y una sola vez.
"""

import uuid

from apps.accounts.models import Role, User
from apps.accounts.roles.services import create_role
from apps.accounts.users.services import set_account_roles

REPORTS_ROLE = "Reportes de campo"


def seed_reports(owner: User, foreman: User) -> list[str]:
    role = Role.objects.filter(producer_id=owner.producer_id, name=REPORTS_ROLE).first()
    if role is None:
        role = create_role(
            owner,
            {
                "name": REPORTS_ROLE,
                "description": "Genera los reportes de lo que ya consulta en su finca.",
                "permission_codes": ["reports.view_producer_reports"],
            },
            uuid.uuid4(),
        )
    roles = list(Role.objects.filter(group__user=foreman))
    if role in roles:
        return []
    set_account_roles(owner, foreman.pk, [item.pk for item in [*roles, role]], uuid.uuid4())
    return [f"Rol «{REPORTS_ROLE}» para el capataz."]
