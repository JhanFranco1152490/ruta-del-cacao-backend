import logging

import pytest
from django.conf import settings

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import LOGIN_URL, open_session

pytestmark = pytest.mark.django_db


def oversized_json_body():
    return '{"note": "' + "a" * (settings.DATA_UPLOAD_MAX_MEMORY_SIZE + 1) + '"}'


@pytest.mark.parametrize("client_fixture", ["api_client", "anonymous_client"])
def test_oversized_json_body_is_a_413_with_the_uniform_error(client_fixture, request, caplog):
    client = request.getfixturevalue(client_fixture)

    with caplog.at_level(logging.WARNING):
        response = client.post(LOGIN_URL, oversized_json_body(), content_type="application/json")

    body = response.json()
    assert response.status_code == 413
    assert set(body) == {"detail", "code", "fields"}
    assert body["code"] == "payload_too_large"
    assert body["detail"]
    assert body["fields"] == {}
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


@pytest.mark.parametrize("client_fixture", ["api_client", "anonymous_client"])
def test_oversized_json_body_with_a_session_is_a_413_before_csrf(client_fixture, request):
    user = UserFactory(permissions=["producers.create"])
    client = open_session(request.getfixturevalue(client_fixture), user)

    response = client.post(
        "/api/producers", oversized_json_body(), content_type="application/json"
    )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"
