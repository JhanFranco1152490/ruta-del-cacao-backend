import pytest

from apps.accounts.tests.factories import UserFactory

ALL_PERMISSIONS = [
    "producers.view",
    "producers.create",
    "producers.update",
    "producers.change_status",
    "producers.delete",
]


@pytest.fixture
def client_with(auth_client):
    def _client(*permissions):
        return auth_client(UserFactory(permissions=list(permissions)))

    return _client


@pytest.fixture
def admin_client(client_with):
    return client_with(*ALL_PERMISSIONS)
