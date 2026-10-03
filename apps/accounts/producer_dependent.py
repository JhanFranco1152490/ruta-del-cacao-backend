from apps.common.producer_dependents import ProducerDependent

from .models import AssociationAccess, Role, User


def _accounts_of(producer):
    return User.objects.filter(producer_id=producer.pk)


def _important_record(producer) -> str | None:
    # Una cuenta que nunca inició sesión se creó por error; una que ya lo hizo es una persona real
    # con historial. El motivo no nombra a nadie: solo cuántas.
    used = _accounts_of(producer).filter(last_login__isnull=False).count()
    if used:
        noun = "cuenta ya inició sesión" if used == 1 else "cuentas ya iniciaron sesión"
        return f"{used} {noun}."
    return None


def _delete_all(producer, actor) -> None:
    _accounts_of(producer).delete()
    # El rol y su grupo: la relación del rol con el grupo es PROTECT, así que primero el rol.
    for role in Role.objects.filter(producer_id=producer.pk).select_related("group"):
        group = role.group
        role.delete()
        group.delete()
    AssociationAccess.objects.filter(producer_id=producer.pk).delete()


accounts_dependent = ProducerDependent(
    name="accounts",
    important_record=_important_record,
    count=lambda producer: _accounts_of(producer).count(),
    delete_all=_delete_all,
)
