import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.inputs.models import AgriculturalInputAuditEvent
from apps.inputs.services import create_input, update_input
from apps.producers.tests.factories import ProducerFactory

from .factories import input_data

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def event():
    owner = UserFactory(producer=ProducerFactory())
    item = create_input(owner, input_data(name="Urea"))
    update_input(owner, item.pk, 1, {"name": "Urea 46 %"})
    return AgriculturalInputAuditEvent.objects.get(action="updated")


def changelist_url():
    return reverse("admin:inputs_agriculturalinputauditevent_changelist")


def change_url(event):
    return reverse("admin:inputs_agriculturalinputauditevent_change", args=[event.pk])


def test_a_superuser_reads_the_history_with_its_values(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    assert client.get(changelist_url()).status_code == 200
    detail = client.get(change_url(event))
    assert detail.status_code == 200
    assert "Urea 46 %" in detail.content.decode()


def test_staff_with_the_inputs_permission_does_not_read_the_history(event):
    # El admin no filtra por productor: con el permiso de la API vería los insumos de todos.
    client = login(UserFactory(is_staff=True, permissions=["inputs.view_agriculturalinput"]))

    assert client.get(changelist_url()).status_code == 403
    assert client.get(change_url(event)).status_code == 403


def test_the_history_cannot_be_changed_from_the_admin(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    add = client.get(reverse("admin:inputs_agriculturalinputauditevent_add"))
    delete = client.post(
        reverse("admin:inputs_agriculturalinputauditevent_delete", args=[event.pk]),
        {"post": "yes"},
    )

    assert add.status_code == 403
    assert delete.status_code == 403
    assert AgriculturalInputAuditEvent.objects.filter(pk=event.pk).exists()
