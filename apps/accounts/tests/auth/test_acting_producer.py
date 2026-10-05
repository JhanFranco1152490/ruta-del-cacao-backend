import uuid

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator, make_producer_owner
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db

ME_URL = "/api/auth/me"


def me(auth_client, user, producer_id):
    return auth_client(user).get(ME_URL, HTTP_X_ACTING_PRODUCER=str(producer_id))


# --- effective_producer_id --------------------------------------------------------------------


def test_the_superuser_acts_under_the_chosen_producer():
    superuser = UserFactory(is_superuser=True)
    producer = ProducerFactory()
    superuser.acting_producer_id = producer.id

    assert superuser.effective_producer_id == producer.id


def test_the_superuser_without_a_choice_has_no_producer():
    assert UserFactory(is_superuser=True).effective_producer_id is None


def test_an_account_that_is_not_a_superuser_ignores_the_acting_producer():
    producer = ProducerFactory()
    owner = make_producer_owner(producer)
    owner.acting_producer_id = ProducerFactory().id

    assert owner.effective_producer_id == producer.id


def test_the_administrator_has_no_effective_producer():
    assert make_administrator().effective_producer_id is None


# --- el encabezado ------------------------------------------------------------------------------


def test_a_superuser_with_a_valid_producer_is_accepted(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = me(auth_client, superuser, ProducerFactory().id)

    assert response.status_code == 200


def test_the_choice_is_never_saved(auth_client):
    superuser = UserFactory(is_superuser=True)

    me(auth_client, superuser, ProducerFactory().id)

    assert User.objects.get(pk=superuser.pk).producer_id is None


def test_an_inactive_producer_is_accepted(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = me(auth_client, superuser, ProducerFactory(status="inactive").id)

    assert response.status_code == 200


def test_an_account_that_is_not_a_superuser_is_refused(auth_client):
    owner = make_producer_owner(ProducerFactory())

    response = me(auth_client, owner, ProducerFactory().id)

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_an_account_that_is_not_a_superuser_is_refused_whatever_the_value(auth_client):
    owner = make_producer_owner(ProducerFactory())

    for value in ("no-es-un-uuid", uuid.uuid4(), ""):
        response = me(auth_client, owner, value)

        assert response.status_code == 403


def test_a_value_that_is_not_a_uuid_is_a_validation_error(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = me(auth_client, superuser, "no-es-un-uuid")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"


def test_a_producer_that_does_not_exist_is_not_found(auth_client):
    superuser = UserFactory(is_superuser=True)

    response = me(auth_client, superuser, uuid.uuid4())

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_without_the_header_nothing_changes(auth_client):
    superuser = UserFactory(is_superuser=True)

    assert auth_client(superuser).get(ME_URL).status_code == 200


# --- la sesión y CORS ---------------------------------------------------------------------------


def test_the_session_says_whether_the_account_is_a_superuser(auth_client):
    superuser = UserFactory(is_superuser=True)
    owner = make_producer_owner(ProducerFactory())

    assert auth_client(superuser).get(ME_URL).data["user"]["is_superuser"] is True
    assert auth_client(owner).get(ME_URL).data["user"]["is_superuser"] is False


def test_the_browser_may_send_the_header(settings):
    assert "x-acting-producer" in settings.CORS_ALLOW_HEADERS
