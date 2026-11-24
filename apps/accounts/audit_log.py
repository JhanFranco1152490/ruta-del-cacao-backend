"""Las cuentas y los roles en la bitácora de cambios, y las cuentas de un productor para filtrar.

Su historial (`AccountManagementEvent`) no es un `AuditEventBase`: dice su acción en
`event_type` y no guarda `changed_fields`, así que sus entradas se arman aquí.
"""

from django.contrib.auth.models import Permission

from apps.common.contracts.audit_log import (
    KIND_BOOL,
    AuditActor,
    AuditEntry,
    AuditSource,
    audit_changes,
    audit_events,
)
from apps.common.serializers import full_name

from .models import AccountManagementEvent, Role, User

EventType = AccountManagementEvent.EventType
ROLE_EVENTS = (EventType.ROLE_CREATED, EventType.ROLE_UPDATED, EventType.ROLE_DELETED)
ACCOUNT_EVENTS = tuple(value for value in EventType.values if value not in ROLE_EVENTS)

ACCOUNT_LABELS = {"roles": "Roles", "all_farms": "Alcanza todas las fincas", "farms": "Fincas"}
ACCOUNT_KINDS = {"all_farms": KIND_BOOL}
ROLE_LABELS = {
    "name": "Nombre",
    "description": "Descripción",
    "farm_scope": "Alcance",
    "permissions": "Permisos",
}
ROLE_NAMES = {"farm_scope": dict(Role.FarmScope.choices)}


def _entry(event, record_type, *, record_id, record_label, record_deleted, changes):
    actor = event.actor
    return AuditEntry(
        id=event.pk,
        occurred_at=event.occurred_at,
        actor_id=event.actor_id,
        actor_name=None if actor is None else full_name(actor),
        record_type=record_type,
        record_id=record_id,
        record_label=record_label,
        record_deleted=record_deleted,
        action=event.event_type,
        action_label=event.get_event_type_display(),
        changes=changes,
    )


def _as_text(changes: dict, field: str, translate=lambda value: value) -> dict:
    """Una lista guardada (roles, fincas, permisos) como texto separado por comas."""
    values = changes.get(field)
    if not values:
        return changes

    def text(items):
        if items is None:
            return None
        return ", ".join(translate(item) for item in items) or "Ninguno"

    return {**changes, field: {side: text(values.get(side)) for side in ("before", "after")}}


def account_events(producer_id, **filters):
    queryset = AccountManagementEvent.objects.filter(event_type__in=ACCOUNT_EVENTS)
    return audit_events(queryset, producer_id, **filters)


def describe_accounts(ids):
    found = AccountManagementEvent.objects.filter(pk__in=ids).select_related(
        "actor", "target_user"
    )
    entries = []
    for event in found:
        target = event.target_user
        changes = _as_text(_as_text(event.changes or {}, "roles"), "farms")
        entries.append(
            _entry(
                event,
                "account",
                record_id=event.target_user_id or event.target_user_ref,
                # El nombre se lee de la cuenta: el historial no guarda datos personales.
                record_label=full_name(target) if target is not None else "Cuenta eliminada",
                record_deleted=target is None,
                changes=audit_changes(changes, labels=ACCOUNT_LABELS, kinds=ACCOUNT_KINDS),
            )
        )
    return entries


def role_events(producer_id, **filters):
    queryset = AccountManagementEvent.objects.filter(event_type__in=ROLE_EVENTS)
    return audit_events(queryset, producer_id, **filters)


def _permission_names(found) -> dict[str, str]:
    """El nombre de cada permiso que aparece en los cambios, en una consulta."""
    codes = set()
    for event in found:
        values = (event.changes or {}).get("permissions") or {}
        for side in ("before", "after"):
            codes.update(values.get(side) or [])
    codenames = {code.split(".", 1)[1] for code in codes if "." in code}
    if not codenames:
        return {}
    permissions = Permission.objects.filter(codename__in=codenames).select_related("content_type")
    return {
        f"{permission.content_type.app_label}.{permission.codename}": permission.name
        for permission in permissions
    }


def _role_label(event, roles: dict) -> str:
    role = roles.get(event.target_role_id)
    if role is not None:
        return role.name
    # Ya se borró: el nombre que guardó el evento.
    values = (event.changes or {}).get("name") or {}
    return values.get("before") or values.get("after") or "Rol eliminado"


def describe_roles(ids):
    found = list(AccountManagementEvent.objects.filter(pk__in=ids).select_related("actor"))
    roles = Role.objects.in_bulk([event.target_role_id for event in found if event.target_role_id])
    permissions = _permission_names(found)
    entries = []
    for event in found:
        changes = _as_text(
            event.changes or {}, "permissions", lambda code: permissions.get(code, code)
        )
        entries.append(
            _entry(
                event,
                "role",
                record_id=event.target_role_id,
                record_label=_role_label(event, roles),
                record_deleted=event.target_role_id not in roles,
                changes=audit_changes(changes, labels=ROLE_LABELS, names=ROLE_NAMES),
            )
        )
    return entries


def producer_accounts(producer_id) -> list[AuditActor]:
    """Las cuentas del productor, activas e inactivas, por nombre: los usuarios por los que se
    puede filtrar la bitácora."""
    accounts = User.objects.filter(producer_id=producer_id).order_by(
        "first_name", "last_name", "email"
    )
    return [
        AuditActor(id=account.pk, full_name=full_name(account), is_active=account.is_active)
        for account in accounts
    ]


ACCOUNT_SOURCE = AuditSource(events=account_events, describe=describe_accounts)
ROLE_SOURCE = AuditSource(events=role_events, describe=describe_roles)
