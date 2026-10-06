import uuid

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.db.models.functions import Lower
from rest_framework.exceptions import ValidationError

from ..access import is_association_admin
from ..authorization import (
    effective_permissions,
    ensure_can_grant,
    ensure_can_manage_role,
    ensure_role_edit_keeps_your_role_management,
)
from ..events import record_account_event
from ..exceptions import DuplicateRoleName, ExceedsOwnPermissions, RoleInUse, RoleNotFound
from ..models import AccountManagementEvent, Role
from ..registry import PERMISSION_DEPENDENCIES, PERMISSION_REGISTRY, with_dependencies
from ..scope import acts_for_producer, visible_roles


def get_role(actor, role_id) -> Role:
    role = visible_roles(actor).filter(pk=role_id).first()
    if role is None:
        raise RoleNotFound()
    return role


def permission_catalog(actor) -> list[dict]:
    # Una sola consulta para todos los permisos existentes; el registro decide cuáles importan.
    all_permissions = {
        f"{permission.content_type.app_label}.{permission.codename}": permission
        for permission in Permission.objects.select_related("content_type")
    }
    granted = effective_permissions(actor)
    results = []
    for code, info in PERMISSION_REGISTRY.items():
        if not info.delegable:
            # Este catálogo solo alimenta la pantalla de crear/editar un rol propio, y un rol
            # propio siempre está atado a un productor (Role.Kind.CUSTOM): un permiso no
            # delegable nunca se le puede asignar a uno, así que ni se ofrece como opción.
            continue
        permission = all_permissions.get(code)
        if permission is None:
            continue
        results.append(
            {
                "code": code,
                "name": permission.name,
                "area": info.area,
                "delegable": info.delegable,
                "grantable": actor.is_superuser or code in granted,
                # Sin este permiso, `roles_manage` (y equivalentes) no sirven de nada: quien
                # los tiene no puede ni consultar lo que gestiona. El frontend lo usa para
                # marcarlo solo, antes de guardar, en vez de que aparezca marcado recién en la
                # respuesta (el backend lo agrega de todas formas si falta, ver with_dependencies).
                "requires": PERMISSION_DEPENDENCIES.get(code),
            }
        )
    return sorted(results, key=lambda item: item["code"])


def _resolve_permissions(codes) -> list[Permission]:
    resolved = []
    for code in codes:
        try:
            app_label, codename = code.split(".")
            resolved.append(
                Permission.objects.get(content_type__app_label=app_label, codename=codename)
            )
        except (ValueError, Permission.DoesNotExist):
            raise ValidationError(
                {"permission_codes": [f"Permiso desconocido: {code}."]}
            ) from None
    return resolved


def _ensure_unique_name(name: str, producer_id, *, exclude_pk=None) -> None:
    # Único sin distinguir mayúsculas entre los roles del sistema y, por separado, dentro de
    # cada productor: la base de datos ya aplica cada una de esas dos, pero no que un rol
    # propio choque con el nombre de uno del sistema, así que se comprueban las dos juntas aquí.
    query = Role.objects.annotate(name_lower=Lower("name")).filter(
        Q(producer_id__isnull=True) | Q(producer_id=producer_id), name_lower=name.lower()
    )
    if exclude_pk is not None:
        query = query.exclude(pk=exclude_pk)
    if query.exists():
        raise DuplicateRoleName()


def create_role(actor, data: dict, request_id) -> Role:
    producer_id = data.get("producer_id")
    if is_association_admin(actor) or actor.is_superuser:
        if producer_id is None:
            raise ValidationError({"producer_id": ["Este campo es requerido."]})
    else:
        if producer_id is not None:
            raise ValidationError({"producer_id": ["Campo no permitido."]})
        producer_id = actor.producer_id
        if producer_id is None:
            raise ValidationError({"producer_id": ["La cuenta no pertenece a ningún productor."]})

    # También cierra el caso de un `producer_id` inexistente: sin un productor real detrás,
    # `acts_for_producer` es falso para todos menos el superusuario.
    if not acts_for_producer(actor, producer_id):
        raise ExceedsOwnPermissions("producer_id")

    # Primero que el código exista de verdad (400): un código desconocido no es lo mismo que
    # uno real que el actor no puede conceder (403), y ensure_can_grant no distingue los dos.
    permission_codes = with_dependencies(data["permission_codes"])
    permissions = _resolve_permissions(permission_codes)
    ensure_can_grant(actor, permission_codes)
    _ensure_unique_name(data["name"], producer_id)

    with transaction.atomic():
        group = Group.objects.create(name=f"role-{uuid.uuid4()}")
        try:
            role = Role.objects.create(
                group=group,
                kind=Role.Kind.CUSTOM,
                producer_id=producer_id,
                name=data["name"],
                description=data["description"],
            )
        except IntegrityError:
            # La única restricción que estos datos pueden violar aquí es el nombre único: el
            # productor ya se verificó arriba y el resto de reglas no dependen de una carrera.
            raise DuplicateRoleName() from None
        group.permissions.set(permissions)
        record_account_event(
            AccountManagementEvent.EventType.ROLE_CREATED,
            request_id,
            actor=actor,
            target_role_id=role.id,
        )
    return role


def update_role(actor, role_id, data: dict, request_id) -> Role:
    role = get_role(actor, role_id)
    ensure_can_manage_role(actor, role)

    if "permission_codes" in data:
        permission_codes = with_dependencies(data["permission_codes"])
        permissions = _resolve_permissions(permission_codes)
        ensure_can_grant(actor, permission_codes)
        ensure_role_edit_keeps_your_role_management(actor, role, permission_codes)
    else:
        permissions = None
    if "name" in data:
        _ensure_unique_name(data["name"], role.producer_id, exclude_pk=role.pk)

    with transaction.atomic():
        changed_fields = [field for field in ("name", "description") if field in data]
        for field in changed_fields:
            setattr(role, field, data[field])
        if changed_fields:
            try:
                role.save(update_fields=changed_fields)
            except IntegrityError:
                raise DuplicateRoleName() from None
        if permissions is not None:
            role.group.permissions.set(permissions)
        record_account_event(
            AccountManagementEvent.EventType.ROLE_UPDATED,
            request_id,
            actor=actor,
            target_role_id=role.id,
        )
    return role


def delete_role(actor, role_id, request_id) -> None:
    role = get_role(actor, role_id)
    ensure_can_manage_role(actor, role)
    if role.group.user_set.exists():
        raise RoleInUse()

    with transaction.atomic():
        group = role.group
        role.delete()
        group.delete()
        record_account_event(
            AccountManagementEvent.EventType.ROLE_DELETED,
            request_id,
            actor=actor,
            target_role_id=role_id,
        )
