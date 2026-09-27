import pytest

from apps.accounts.access import is_effectively_active
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import login_by_email
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

REFRESH_URL = "/api/auth/refresh"
ME_URL = "/api/auth/me"

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "is_active, producer_status, expected",
    [
        (True, None, True),
        (False, None, False),
        (True, Producer.Status.ACTIVE, True),
        (True, Producer.Status.INACTIVE, False),
        (False, Producer.Status.ACTIVE, False),
    ],
)
def test_is_effectively_active(is_active, producer_status, expected):
    producer = ProducerFactory(status=producer_status) if producer_status else None
    user = UserFactory(is_active=is_active, producer=producer)

    assert is_effectively_active(user) is expected


def test_login_with_correct_password_and_inactive_producer_is_account_inactive(api_client):
    user = UserFactory(producer=ProducerFactory(status=Producer.Status.INACTIVE))

    response = login_by_email(api_client, user.email)

    assert response.status_code == 403
    assert response.data["code"] == "account_inactive"


def test_login_with_wrong_password_and_inactive_producer_is_invalid_credentials(api_client):
    user = UserFactory(producer=ProducerFactory(status=Producer.Status.INACTIVE))

    response = login_by_email(api_client, user.email, password="una contraseña incorrecta")

    assert response.status_code == 401
    assert response.data["code"] == "invalid_credentials"


def test_valid_access_token_is_rejected_after_the_producer_is_deactivated(auth_client):
    producer = ProducerFactory()
    client = auth_client(UserFactory(producer=producer))

    producer.status = Producer.Status.INACTIVE
    producer.save(update_fields=["status"])

    response = client.get(ME_URL)

    assert response.status_code == 401
    assert response.data["code"] == "authentication_failed"


def test_refresh_is_rejected_after_the_producer_is_deactivated(auth_client):
    producer = ProducerFactory()
    client = auth_client(UserFactory(producer=producer))

    producer.status = Producer.Status.INACTIVE
    producer.save(update_fields=["status"])

    response = client.post(REFRESH_URL)

    assert response.status_code == 401
    assert response.cookies["cacao_access"].value == ""
    assert response.cookies["cacao_refresh"].value == ""


def test_reactivating_the_producer_restores_access_without_logging_in_again(auth_client):
    producer = ProducerFactory()
    client = auth_client(UserFactory(producer=producer))
    refresh = client.cookies["cacao_refresh"].value

    producer.status = Producer.Status.INACTIVE
    producer.save(update_fields=["status"])
    assert client.post(REFRESH_URL).status_code == 401

    producer.status = Producer.Status.ACTIVE
    producer.save(update_fields=["status"])
    # El rechazo anterior borró la cookie del cliente de prueba (como haría el navegador); se
    # restaura el mismo token de renovación, que sigue vigente porque el rechazo ocurrió antes
    # de rotarlo: nadie tuvo que volver a iniciar sesión.
    client.cookies["cacao_refresh"] = refresh

    assert client.post(REFRESH_URL).status_code == 204
