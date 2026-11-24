"""Los valores en el historial de cuentas y roles: los roles y las fincas de una cuenta, y el
nombre, el alcance y los permisos de un rol, antes y después."""

import uuid

import pytest

from apps.accounts.models import AccountManagementEvent
from apps.accounts.roles.services import update_role
from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_producer_owner
from apps.accounts.users.services import set_account_roles
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

EventType = AccountManagementEvent.EventType
VIEW_FARM = "farms.view_farm"


def _last(event_type):
    return AccountManagementEvent.objects.filter(event_type=event_type).latest("occurred_at")


def test_changing_the_roles_keeps_their_names_before_and_after():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    before = RoleFactory(producer=producer, name="Recolector", permissions=[VIEW_FARM])
    after = RoleFactory(producer=producer, name="Capataz de campo", permissions=[VIEW_FARM])
    employee = grant_role(UserFactory(producer=producer, all_farms=True), before)

    set_account_roles(owner, employee.pk, [after.pk], uuid.uuid4())

    assert _last(EventType.ACCOUNT_ROLES_CHANGED).changes == {
        "roles": {"before": ["Recolector"], "after": ["Capataz de campo"]}
    }


def test_editing_a_role_keeps_what_changed():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, name="Recolector", permissions=[VIEW_FARM])

    update_role(owner, role.pk, {"name": "Recolector de campo"}, uuid.uuid4())

    assert _last(EventType.ROLE_UPDATED).changes == {
        "name": {"before": "Recolector", "after": "Recolector de campo"}
    }


def test_editing_the_permissions_of_a_role_keeps_their_codes():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    role = RoleFactory(producer=producer, permissions=[VIEW_FARM])

    update_role(owner, role.pk, {"permission_codes": [VIEW_FARM, "plots.view_plot"]}, uuid.uuid4())

    assert _last(EventType.ROLE_UPDATED).changes["permissions"] == {
        "before": [VIEW_FARM],
        "after": [VIEW_FARM, "plots.view_plot"],
    }
