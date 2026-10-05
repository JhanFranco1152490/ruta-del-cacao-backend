from functools import partial

from django.db import transaction
from django.db.models import QuerySet

from apps.common.audit import record_update_events
from apps.common.db import save_translating_unique

from ..exceptions import DuplicateVarietyName, VarietyNotFound
from ..models import CacaoVariety, CacaoVarietyAuditEvent
from ..text import normalize_variety_name
from .audit import record_variety_audit_event

NAME_UNIQUE_CONSTRAINT = "crops_variety_name_normalized_unique"
CONTENT_FIELDS = ("name", "common_names", "description")


def list_varieties(is_active: bool | None = None, search: str | None = None) -> QuerySet:
    varieties = CacaoVariety.objects.order_by("name_normalized", "id")
    if is_active is not None:
        varieties = varieties.filter(is_active=is_active)
    # Se busca como se comparan los nombres del catálogo, también en los nombres comunes: "ccn 51"
    # encuentra "CCN-51" y "saravena" encuentra los tres FSA.
    term = normalize_variety_name(search or "")
    if term:
        varieties = varieties.filter(search_normalized__contains=term)
    return varieties


def name_taken(name: str, exclude_id=None) -> bool:
    """Si otra variedad ya usa ese nombre, comparado como lo compara el catálogo."""
    others = CacaoVariety.objects.filter(name_normalized=normalize_variety_name(name))
    if exclude_id is not None:
        others = others.exclude(pk=exclude_id)
    return others.exists()


@transaction.atomic
def create_variety(actor, data: dict) -> CacaoVariety:
    # `is_active` solo llega desde el admin; la API registra siempre activas.
    variety = CacaoVariety(
        name=data["name"],
        common_names=data.get("common_names", []),
        description=data.get("description", ""),
        is_active=data.get("is_active", True),
    )
    variety.full_clean(validate_unique=False, validate_constraints=False)
    _save(variety)
    record_variety_audit_event(
        variety=variety, actor=actor, action=CacaoVarietyAuditEvent.Action.CREATED
    )
    return variety


@transaction.atomic
def update_variety(actor, variety_id, data: dict) -> CacaoVariety:
    """Edita el nombre o la descripción, o activa y desactiva. Desactivar no toca las fichas que
    ya la usan: solo deja de ofrecerse para siembras nuevas."""
    variety = CacaoVariety.objects.select_for_update().filter(pk=variety_id).first()
    if variety is None:
        raise VarietyNotFound()

    before = {name: getattr(variety, name) for name in (*CONTENT_FIELDS, "is_active")}
    for name, value in data.items():
        setattr(variety, name, value)
    variety.full_clean(validate_unique=False, validate_constraints=False)
    # Se compara después de validar: un nombre que solo cambió en espacios no es un cambio. Lo
    # mismo con los nombres comunes, que `clean()` limpia y deja sin repetidos.
    changed = [name for name in before if getattr(variety, name) != before[name]]
    if not changed:
        return variety

    update_fields = [*changed, "updated_at"]
    if "name" in changed:
        update_fields.append("name_normalized")
    if "name" in changed or "common_names" in changed:
        update_fields.append("search_normalized")
    _save(variety, update_fields=update_fields)

    record_update_events(
        partial(record_variety_audit_event, variety=variety, actor=actor),
        changed,
        updated=CacaoVarietyAuditEvent.Action.UPDATED,
        status_changed=CacaoVarietyAuditEvent.Action.STATUS_CHANGED,
    )
    return variety


@transaction.atomic
def delete_variety(actor, variety: CacaoVariety) -> None:
    """Elimina una variedad registrada por error. Si alguna ficha la usa, la base lo impide
    (`ProtectedError`) y el evento se revierte con todo lo demás. El historial se conserva."""
    record_variety_audit_event(
        variety=variety, actor=actor, action=CacaoVarietyAuditEvent.Action.DELETED
    )
    variety.delete()


def _save(variety: CacaoVariety, update_fields=None) -> None:
    save_translating_unique(
        lambda: variety.save(update_fields=update_fields),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=DuplicateVarietyName,
    )
