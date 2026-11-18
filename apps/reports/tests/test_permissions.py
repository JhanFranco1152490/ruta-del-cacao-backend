import pytest
from django.apps import apps
from django.contrib.auth.models import Permission

from apps.accounts import registry
from apps.accounts.apps import last_app_with_models
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

PRODUCER_REPORTS = "reports.view_producer_reports"
ASSOCIATION_REPORTS = "reports.view_association_reports"


def codes_of(role_code):
    return set(get_system_role(role_code).permission_codes)


@pytest.mark.parametrize("codename", ["view_producer_reports", "view_association_reports"])
def test_the_two_permissions_exist_after_migrating(codename):
    assert Permission.objects.filter(content_type__app_label="reports", codename=codename).exists()


def test_reports_is_the_last_app_with_models_so_the_roles_sync_after_it():
    assert last_app_with_models(apps.get_app_configs()).label == "reports"


def test_the_producer_reports_are_a_delegable_field_permission_without_dependencies():
    assert registry.is_delegable(PRODUCER_REPORTS)
    # Cuelga de las fincas: un empleado que lo tenga necesita una finca para ver algo.
    assert registry.is_field_permission(PRODUCER_REPORTS)
    assert registry.area_of(PRODUCER_REPORTS) == "reports"
    # Cada tipo de reporte pide además el permiso de su módulo al generarse, no al delegarse.
    assert registry.with_dependencies({PRODUCER_REPORTS}) == {PRODUCER_REPORTS}


def test_the_association_reports_are_not_delegable():
    assert not registry.is_delegable(ASSOCIATION_REPORTS)
    assert not registry.is_field_permission(ASSOCIATION_REPORTS)
    assert registry.area_of(ASSOCIATION_REPORTS) == "reports"
    assert registry.with_dependencies({ASSOCIATION_REPORTS}) == {ASSOCIATION_REPORTS}


def test_the_producer_gets_its_reports_and_not_the_association_ones():
    assert PRODUCER_REPORTS in codes_of(PRODUCER)
    assert ASSOCIATION_REPORTS not in codes_of(PRODUCER)


def test_the_association_gets_its_reports_and_not_the_producer_ones():
    assert ASSOCIATION_REPORTS in codes_of(ADMINISTRATOR)
    assert PRODUCER_REPORTS not in codes_of(ADMINISTRATOR)


@pytest.mark.parametrize("role", [FOREMAN, QUALITY_MANAGER, SALES_MANAGER])
def test_no_predefined_employee_role_brings_reports(role):
    assert not {code for code in codes_of(role) if code.startswith("reports.")}


def test_a_producer_cannot_put_the_association_reports_in_its_own_role(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Reportes de todos", "permission_codes": [ASSOCIATION_REPORTS]},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"


def test_a_producer_can_delegate_its_reports_in_its_own_role(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Ver reportes", "permission_codes": [PRODUCER_REPORTS]},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["permissions"] == [PRODUCER_REPORTS]
