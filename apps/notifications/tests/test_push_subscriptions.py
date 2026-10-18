import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import open_session
from apps.notifications.models import PushSubscription
from apps.notifications.tests.factories import PushSubscriptionFactory

pytestmark = pytest.mark.django_db

CONFIG_URL = "/api/notifications/push-config"
URL = "/api/notifications/push-subscriptions"
REMOVE_URL = "/api/notifications/push-subscriptions/remove"
ENDPOINT = "https://fcm.googleapis.com/fcm/send/dQw4w9WgXcQ:APA91bH"
KEYS = {
    "p256dh": (
        "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM"
    ),
    "auth": "tBHItJI5svbpez7KI4CCXg",
}


def body(**overrides):
    return {"endpoint": ENDPOINT, "keys": KEYS, "device_label": "Chrome en Android", **overrides}


# La llave pública.


@pytest.fixture
def vapid(settings):
    settings.VAPID_PUBLIC_KEY = "BPublica"
    settings.VAPID_PRIVATE_KEY = "privada"
    settings.VAPID_SUBJECT = "mailto:equipo@example.com"


@pytest.mark.usefixtures("vapid")
def test_the_public_key_comes_from_the_settings(auth_client):

    response = auth_client(UserFactory()).get(CONFIG_URL)

    assert response.status_code == 200
    assert response.data == {"public_key": "BPublica"}


@pytest.mark.usefixtures("vapid")
@pytest.mark.parametrize("missing", ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT"])
def test_push_is_not_offered_unless_it_can_be_sent(auth_client, settings, missing):
    setattr(settings, missing, "")

    assert auth_client(UserFactory()).get(CONFIG_URL).data == {"public_key": None}


def test_the_config_needs_a_session(anonymous_client):
    assert anonymous_client.get(CONFIG_URL).status_code == 401


# Activar en un dispositivo.


def test_a_device_subscribes(auth_client):
    user = UserFactory()

    response = auth_client(user).post(URL, body(), format="json")

    assert response.status_code == 201
    assert set(response.data) == {"id", "device_label", "created_at"}
    subscription = PushSubscription.objects.get()
    assert (subscription.user, subscription.endpoint) == (user, ENDPOINT)
    assert (subscription.p256dh, subscription.auth) == (KEYS["p256dh"], KEYS["auth"])
    assert subscription.device_label == "Chrome en Android"


def test_subscribing_again_updates_the_same_device(auth_client):
    user = UserFactory()
    client = auth_client(user)
    client.post(URL, body(), format="json")

    response = client.post(
        URL, body(keys={**KEYS, "auth": "otraLlaveAuth"}, device_label=None), format="json"
    )

    assert response.status_code == 200
    subscription = PushSubscription.objects.get()
    assert subscription.auth == "otraLlaveAuth"
    assert subscription.device_label is None


def test_a_device_used_by_someone_else_moves_to_the_current_account(auth_client):
    before = PushSubscriptionFactory(endpoint=ENDPOINT)
    now = UserFactory()

    response = auth_client(now).post(URL, body(), format="json")

    assert response.status_code == 200
    assert PushSubscription.objects.get(pk=before.pk).user == now


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://example.com/push",
        "https://fcm.googleapis.com.example.com/x",
        "https://127.0.0.1/push",
        "no es una url",
    ],
)
def test_only_real_push_services_are_accepted(auth_client, endpoint):
    response = auth_client(UserFactory()).post(URL, body(endpoint=endpoint), format="json")

    assert (response.status_code, list(response.data["fields"])) == (400, ["endpoint"])
    assert not PushSubscription.objects.exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGuQ",
        "https://wns2-by3p.notify.windows.com/w/?token=abc",
    ],
)
def test_the_push_services_of_each_browser_are_accepted(auth_client, endpoint):
    response = auth_client(UserFactory()).post(URL, body(endpoint=endpoint), format="json")

    assert response.status_code == 201


@pytest.mark.parametrize("missing", ["p256dh", "auth"])
def test_both_keys_are_needed(auth_client, missing):
    keys = {name: value for name, value in KEYS.items() if name != missing}

    response = auth_client(UserFactory()).post(URL, body(keys=keys), format="json")

    assert response.status_code == 400


def test_unknown_fields_are_rejected(auth_client):
    response = auth_client(UserFactory()).post(URL, body(user_id=1), format="json")

    assert response.status_code == 400


# Desactivar en un dispositivo.


def test_removing_a_device(auth_client):
    subscription = PushSubscriptionFactory(endpoint=ENDPOINT)

    response = auth_client(subscription.user).post(
        REMOVE_URL, {"endpoint": ENDPOINT}, format="json"
    )

    assert response.status_code == 204
    assert not PushSubscription.objects.exists()


def test_removing_a_device_that_is_not_there_is_fine(auth_client):
    response = auth_client(UserFactory()).post(REMOVE_URL, {"endpoint": ENDPOINT}, format="json")

    assert response.status_code == 204


def test_nobody_removes_someone_elses_device(auth_client):
    theirs = PushSubscriptionFactory(endpoint=ENDPOINT)

    auth_client(UserFactory()).post(REMOVE_URL, {"endpoint": ENDPOINT}, format="json")

    assert PushSubscription.objects.filter(pk=theirs.pk).exists()


def test_writing_needs_the_csrf_token():
    client = open_session(APIClient(enforce_csrf_checks=True), UserFactory())

    assert client.post(URL, body(), format="json").status_code == 403
    assert client.post(REMOVE_URL, {"endpoint": ENDPOINT}, format="json").status_code == 403
    assert not PushSubscription.objects.exists()
