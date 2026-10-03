import pytest
from drf_spectacular.generators import SchemaGenerator
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    enable_association_access,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.common.csrf import CSRF_FAILED_DETAIL
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def client(auth_client, producer):
    return auth_client(make_producer_owner(producer))


def delete(client, farm, version=1):
    return client.delete(f"/api/farms/{farm.id}?expected_version={version}")


def test_deletes_a_farm_without_business_records(client, producer):
    farm = FarmFactory(producer=producer)

    response = delete(client, farm)

    assert response.status_code == 204
    assert not Farm.objects.filter(pk=farm.id).exists()
    assert FarmAuditEvent.objects.get(farm_ref=farm.id).action == FarmAuditEvent.Action.DELETED


def test_a_farm_with_business_records_is_kept(client, producer, farm_dependent_model):
    farm = FarmFactory(producer=producer)
    farm_dependent_model.objects.create(farm=farm)

    response = delete(client, farm)

    assert response.status_code == 409
    assert response.data["code"] == "farm_has_records"
    assert Farm.objects.filter(pk=farm.id).exists()


def test_deleting_with_a_stale_version_returns_the_current_farm(client, producer):
    farm = FarmFactory(producer=producer, version=2)

    response = delete(client, farm, version=1)

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2


def test_deleting_requires_the_expected_version(client, producer):
    farm = FarmFactory(producer=producer)

    response = client.delete(f"/api/farms/{farm.id}")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]
    assert Farm.objects.filter(pk=farm.id).exists()


def test_deleting_requires_the_delete_permission(auth_client, producer):
    editor = UserFactory(producer=producer, permissions=["farms.view_farm", "farms.change_farm"])
    farm = FarmFactory(producer=producer)

    response = delete(auth_client(editor), farm)

    assert response.status_code == 403
    assert Farm.objects.filter(pk=farm.id).exists()


def test_a_farm_of_another_producer_is_not_found(client):
    farm = FarmFactory(producer=ProducerFactory())

    response = delete(client, farm)

    assert response.status_code == 404
    assert Farm.objects.filter(pk=farm.id).exists()


def test_deleting_requires_csrf(anonymous_client, producer):
    owner = make_producer_owner(producer)
    farm = FarmFactory(producer=producer)
    anonymous_client.cookies["cacao_access"] = str(RefreshToken.for_user(owner).access_token)

    response = delete(anonymous_client, farm)

    assert response.status_code == 403
    assert response.data["detail"] == CSRF_FAILED_DETAIL
    assert Farm.objects.filter(pk=farm.id).exists()


def test_an_employee_deletes_when_the_producer_delegated_it(auth_client, producer):
    employee = make_delegate(producer, ["farms.delete_farm"])
    farm = FarmFactory(producer=producer)

    response = delete(auth_client(employee), farm)

    assert response.status_code == 204
    assert not Farm.objects.filter(pk=farm.id).exists()


def test_the_association_cannot_delete_farms(auth_client, producer):
    # La asociación solo lee las fincas, incluso si el productor le abrió su espacio.
    enable_association_access(producer)
    farm = FarmFactory(producer=producer)

    response = delete(auth_client(make_administrator()), farm)

    assert response.status_code == 403
    assert Farm.objects.filter(pk=farm.id).exists()


def test_the_schema_documents_the_expected_version_of_a_delete():
    # Va en la URL y no en el cuerpo: el esquema no documenta cuerpos en DELETE, así que el
    # cliente generado no lo enviaría, y algunos intermediarios descartan ese cuerpo.
    operation = SchemaGenerator().get_schema(public=True)["paths"]["/api/farms/{id}"]["delete"]

    parameter = next(p for p in operation["parameters"] if p["name"] == "expected_version")
    assert (parameter["in"], parameter["required"]) == ("query", True)
    assert "requestBody" not in operation
