import pytest

from apps.accounts.tests.factories import RoleFactory, UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def test_the_active_producer_does_not_limit_the_user_list(auth_client):
    superuser = UserFactory(is_superuser=True)
    chosen, other = ProducerFactory(), ProducerFactory()
    make_producer_owner(chosen)
    other_owner = make_producer_owner(other)

    response = auth_client(superuser).get("/api/users", HTTP_X_ACTING_PRODUCER=str(chosen.id))

    assert str(other_owner.id) in {item["id"] for item in response.data["results"]}


def test_the_active_producer_does_not_limit_the_role_list(auth_client):
    superuser = UserFactory(is_superuser=True)
    other_role = RoleFactory(producer=ProducerFactory())

    response = auth_client(superuser).get(
        "/api/roles", HTTP_X_ACTING_PRODUCER=str(ProducerFactory().id)
    )

    assert str(other_role.id) in {item["id"] for item in response.data["results"]}
