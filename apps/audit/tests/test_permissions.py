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

AUDIT_LOG = "audit.view_audit_log"


def codes_of(role_code):
    return set(get_system_role(role_code).permission_codes)


def test_the_permission_exists_after_migrating():
    assert Permission.objects.filter(
        content_type__app_label="audit", codename="view_audit_log"
    ).exists()


def test_audit_is_the_last_app_with_models_so_the_roles_sync_after_it():
    assert last_app_with_models(apps.get_app_configs()).label == "audit"


def test_the_audit_log_is_not_delegable_and_not_a_field_permission():
    assert not registry.is_delegable(AUDIT_LOG)
    # Es de toda la unidad productiva, no de una finca.
    assert not registry.is_field_permission(AUDIT_LOG)
    assert registry.area_of(AUDIT_LOG) == "audit"
    assert registry.with_dependencies({AUDIT_LOG}) == {AUDIT_LOG}


def test_only_the_producer_role_brings_the_audit_log():
    assert AUDIT_LOG in codes_of(PRODUCER)


@pytest.mark.parametrize("role", [ADMINISTRATOR, FOREMAN, QUALITY_MANAGER, SALES_MANAGER])
def test_no_other_system_role_brings_the_audit_log(role):
    assert AUDIT_LOG not in codes_of(role)


def test_a_producer_cannot_put_the_audit_log_in_its_own_role(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = auth_client(owner).post(
        "/api/roles",
        {"name": "Ver la bitácora", "permission_codes": [AUDIT_LOG]},
        format="json",
    )

    assert response.status_code == 403
    assert response.data["code"] == "exceeds_own_permissions"
