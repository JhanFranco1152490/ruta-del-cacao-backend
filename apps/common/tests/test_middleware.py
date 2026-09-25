import pytest

pytestmark = pytest.mark.django_db


def test_api_responses_are_never_cached(client):
    response = client.get("/api/auth/csrf")

    assert "no-store" in response["Cache-Control"]


def test_non_api_responses_are_left_alone(client):
    response = client.get("/ruta-que-no-existe")

    assert "no-store" not in response.get("Cache-Control", "")
