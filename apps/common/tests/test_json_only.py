import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.helpers import LOGIN_URL, open_session

pytestmark = pytest.mark.django_db

CSRF_URL = "/api/auth/csrf"
PRODUCERS_URL = "/api/producers"
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


def assert_error_shape(response, status_code, code):
    assert response.status_code == status_code
    assert response["Content-Type"].startswith("application/json")
    body = response.json()
    assert set(body) == {"detail", "code", "fields"}
    assert body["code"] == code
    assert isinstance(body["detail"], str) and body["detail"]
    assert body["fields"] == {}


def test_urlencoded_body_is_rejected_with_the_uniform_error(api_client):
    response = api_client.post(
        LOGIN_URL,
        "login_method=email&email=ana%40example.com&password=x",
        content_type="application/x-www-form-urlencoded",
    )

    assert_error_shape(response, 415, "unsupported_media_type")


def test_multipart_body_is_rejected_with_the_uniform_error(api_client):
    response = api_client.post(
        LOGIN_URL,
        {"login_method": "email", "email": "ana@example.com", "password": "x"},
        format="multipart",
    )

    assert_error_shape(response, 415, "unsupported_media_type")


@pytest.mark.parametrize("client_fixture", ["api_client", "anonymous_client"])
@pytest.mark.parametrize(
    ("body", "status_code", "code"),
    [
        ({"data": {"first_name": "Ana"}, "format": "multipart"}, 415, "unsupported_media_type"),
        ({"data": '{"first_name": ', "content_type": "application/json"}, 400, "parse_error"),
    ],
)
def test_body_errors_with_a_session_are_answered_before_csrf(
    request, client_fixture, body, status_code, code
):
    user = UserFactory(permissions=["producers.create"])
    client = open_session(request.getfixturevalue(client_fixture), user)

    response = client.post(PRODUCERS_URL, **body)

    assert_error_shape(response, status_code, code)


def test_html_is_never_rendered_for_an_html_only_accept(anonymous_client):
    response = anonymous_client.get(CSRF_URL, HTTP_ACCEPT="text/html")

    assert_error_shape(response, 406, "not_acceptable")


def test_browser_navigation_gets_json_and_not_the_browsable_api(anonymous_client):
    response = anonymous_client.get(CSRF_URL, HTTP_ACCEPT=BROWSER_ACCEPT)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    assert "csrf_token" in response.json()
