import uuid

import pytest
from django.utils import timezone

from apps.accounts.registry import PERMISSION_REGISTRY, is_delegable
from apps.accounts.system_roles import PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_delegate
from apps.farms.tests.factories import FarmFactory
from apps.producers.models import Producer, ProducerAuditEvent
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def _url(producer, version="1"):
    suffix = f"?expected_version={version}" if version is not None else ""
    return f"/api/producers/{producer.id}{suffix}"


@pytest.fixture
def association(auth_client):
    return auth_client(make_administrator())


def test_the_association_deletes_a_producer_created_by_mistake(association):
    producer = ProducerFactory()

    response = association.delete(_url(producer))

    assert response.status_code == 204
    assert not response.content
    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert association.get("/api/producers").data["count"] == 0
    assert ProducerAuditEvent.objects.get().member_code == producer.member_code


def test_its_farms_go_with_it_and_stop_showing_in_the_farm_list(association):
    producer = ProducerFactory()
    FarmFactory(producer=producer)

    association.delete(_url(producer))

    assert association.get("/api/farms").data["count"] == 0


def test_the_version_must_come_in_the_url(association):
    producer = ProducerFactory()

    response = association.delete(_url(producer, version=None))

    assert response.status_code == 400
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_a_stale_version_is_a_conflict_and_deletes_nothing(association):
    producer = ProducerFactory()

    response = association.delete(_url(producer, version=5))

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_a_producer_whose_owner_already_signed_in_answers_has_records(association):
    producer = ProducerFactory(email="duena@example.com")
    owner = producer.accounts.get()
    owner.last_login = timezone.now()
    owner.save(update_fields=["last_login"])

    response = association.delete(_url(producer))

    assert response.status_code == 409
    assert response.data["code"] == "producer_has_records"
    assert "ya inició sesión" in response.data["detail"]
    assert "duena@example.com" not in response.data["detail"]
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_a_producer_that_does_not_exist_is_not_found(association):
    response = association.delete(f"/api/producers/{uuid.uuid4()}?expected_version=1")

    assert response.status_code == 404


def test_it_needs_a_session(api_client):
    producer = ProducerFactory()

    response = api_client.delete(_url(producer))

    assert response.status_code == 401


def test_the_permission_is_not_delegable():
    assert PERMISSION_REGISTRY["producers.delete"].delegable is False
    assert is_delegable("producers.delete") is False


def test_a_producer_cannot_delete_even_its_own_record(auth_client):
    producer = ProducerFactory()
    owner = grant_role(UserFactory(producer=producer), get_system_role(PRODUCER))

    response = auth_client(owner).delete(_url(producer))

    assert response.status_code == 403
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_an_employee_with_every_delegable_permission_cannot_either(auth_client):
    producer = ProducerFactory()
    delegable = [code for code in PERMISSION_REGISTRY if is_delegable(code)]
    employee = make_delegate(producer, delegable)

    response = auth_client(employee).delete(_url(producer))

    assert response.status_code == 403
    assert Producer.objects.filter(pk=producer.pk).exists()
