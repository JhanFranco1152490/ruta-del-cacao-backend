import pytest
from django.contrib.auth.models import Permission

from apps.accounts import registry
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
    get_system_role,
)
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

PRODUCER_PANEL = "indicators.view_producer_indicators"
ASSOCIATION_PANEL = "indicators.view_association_indicators"


def codes_of(role_code):
    return set(get_system_role(role_code).permission_codes)


@pytest.mark.parametrize("codename", ["view_producer_indicators", "view_association_indicators"])
def test_the_two_permissions_exist_after_migrating(codename):
    assert Permission.objects.filter(
        content_type__app_label="indicators", codename=codename
    ).exists()


def test_the_producer_panel_is_a_delegable_field_permission_without_dependencies():
    assert registry.is_delegable(PRODUCER_PANEL)
    # Cuelga de las fincas: un empleado que lo tenga necesita una finca para ver algo.
    assert registry.is_field_permission(PRODUCER_PANEL)
    assert registry.area_of(PRODUCER_PANEL) == "indicators"
    assert registry.with_dependencies({PRODUCER_PANEL}) == {PRODUCER_PANEL}


def test_the_association_panel_is_not_delegable():
    assert not registry.is_delegable(ASSOCIATION_PANEL)
    assert not registry.is_field_permission(ASSOCIATION_PANEL)
    assert registry.area_of(ASSOCIATION_PANEL) == "indicators"
    assert registry.with_dependencies({ASSOCIATION_PANEL}) == {ASSOCIATION_PANEL}


def test_the_producer_sees_its_panel_and_not_the_association_one():
    assert PRODUCER_PANEL in codes_of(PRODUCER)
    assert ASSOCIATION_PANEL not in codes_of(PRODUCER)


def test_the_association_sees_its_panel_and_not_the_producer_one():
    assert ASSOCIATION_PANEL in codes_of(ADMINISTRATOR)
    assert PRODUCER_PANEL not in codes_of(ADMINISTRATOR)


@pytest.mark.parametrize("role", [FOREMAN, QUALITY_MANAGER, SALES_MANAGER])
def test_no_predefined_employee_role_brings_a_panel(role):
    assert not {code for code in codes_of(role) if code.startswith("indicators.")}


def test_a_producer_cannot_put_the_association_panel_in_its_own_role(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Indicadores de todos", "permission_codes": [ASSOCIATION_PANEL]},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_a_producer_can_delegate_its_panel_in_its_own_role(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Ver indicadores", "permission_codes": [PRODUCER_PANEL]},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["permissions"] == [PRODUCER_PANEL]
