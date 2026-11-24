"""Las cuentas y los roles en la bitácora, y las cuentas del productor para filtrar."""

import uuid

import pytest

from apps.accounts.events import record_account_event
from apps.accounts.models import AccountManagementEvent
from apps.accounts.roles.services import delete_role, update_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.accounts.users.services import set_account_roles
from apps.common.contracts.audit_log import AuditActor, audit_actors, audit_source
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

EventType = AccountManagementEvent.EventType
VIEW_FARM = "farms.view_farm"


def _last(event_type):
    return AccountManagementEvent.objects.filter(event_type=event_type).latest("occurred_at")


def _describe(record_type, event):
    [entry] = audit_source(record_type).describe([event.pk])
    return entry


def test_a_roles_change_names_the_account_and_both_role_lists():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    before = RoleFactory(producer=producer, name="Recolector", permissions=[VIEW_FARM])
    after = RoleFactory(producer=producer, name="Capataz de campo", permissions=[VIEW_FARM])
    employee = grant_role(
        UserFactory(producer=producer, all_farms=True, first_name="Luis", last_name="Peña"),
        before,
    )
    set_account_roles(owner, employee.pk, [after.pk], uuid.uuid4())

    entry = _describe("account", _last(EventType.ACCOUNT_ROLES_CHANGED))

    assert (entry.record_type, entry.record_label, entry.action_label) == (
        "account",
        "Luis Peña",
        "Roles de la cuenta cambiados",
    )
    assert (entry.actor_id, entry.record_id) == (owner.pk, employee.pk)
    [change] = entry.changes
    assert (change.label, change.before, change.after) == (
        "Roles",
        "Recolector",
        "Capataz de campo",
    )


def test_a_role_edit_shows_its_permissions_by_name():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, name="Recolector", permissions=[VIEW_FARM])
    update_role(owner, role.pk, {"permission_codes": [VIEW_FARM, "plots.view_plot"]}, uuid.uuid4())

    entry = _describe("role", _last(EventType.ROLE_UPDATED))

    assert entry.record_label == "Recolector"
    [change] = entry.changes
    assert change.label == "Permisos"
    assert "Puede consultar parcelas" in change.after
    assert "Puede consultar parcelas" not in change.before


def test_a_deleted_role_is_named_by_what_its_event_kept():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, name="Temporal", permissions=[VIEW_FARM])
    delete_role(owner, role.pk, uuid.uuid4())

    entry = _describe("role", _last(EventType.ROLE_DELETED))

    assert (entry.record_label, entry.record_deleted) == ("Temporal", True)


def test_a_deleted_account_has_no_name():
    record_account_event(
        EventType.ACCOUNT_DELETED,
        uuid.uuid4(),
        target_user_ref=uuid.uuid4(),
        producer_ref=ProducerFactory().pk,
    )

    entry = _describe("account", _last(EventType.ACCOUNT_DELETED))

    assert (entry.record_label, entry.record_deleted) == ("Cuenta eliminada", True)


def test_account_and_role_events_go_to_their_own_type():
    producer = ProducerFactory()
    employee = UserFactory(producer=producer)
    role = RoleFactory(producer=producer)
    record_account_event(EventType.ACCOUNT_DEACTIVATED, uuid.uuid4(), target_user=employee)
    record_account_event(EventType.ROLE_UPDATED, uuid.uuid4(), target_role_id=role.pk)

    accounts = list(audit_source("account").events(producer.pk))
    roles = list(audit_source("role").events(producer.pk))

    assert [row["id"] for row in accounts] == [_last(EventType.ACCOUNT_DEACTIVATED).pk]
    assert [row["id"] for row in roles] == [_last(EventType.ROLE_UPDATED).pk]


def test_the_actors_are_the_accounts_of_the_producer_also_inactive_by_name():
    producer = ProducerFactory()
    ana = UserFactory(producer=producer, first_name="Ana", last_name="Ruiz")
    luis = UserFactory(producer=producer, first_name="Luis", last_name="Peña", is_active=False)
    UserFactory(producer=ProducerFactory())

    assert audit_actors(producer.pk) == [
        AuditActor(id=ana.pk, full_name="Ana Ruiz", is_active=True),
        AuditActor(id=luis.pk, full_name="Luis Peña", is_active=False),
    ]
