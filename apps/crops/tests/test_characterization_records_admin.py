import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.crops.models import CacaoVarietyAuditEvent
from apps.crops.services import create_variety

from .factories import PlotCharacterizationFactory, PlotPlantingFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    return login(superuser)


def test_the_characterization_shows_its_plantings_and_nothing_can_be_edited(client):
    planting = PlotPlantingFactory(tree_count=600)
    characterization = planting.characterization
    url = reverse("admin:crops_plotcharacterization_change", args=[characterization.pk])

    body = client.get(url).content.decode()

    assert planting.variety.name in body
    assert "600" in body
    assert client.get(reverse("admin:crops_plotcharacterization_changelist")).status_code == 200
    assert client.get(reverse("admin:crops_plotcharacterization_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    deletion = reverse("admin:crops_plotcharacterization_delete", args=[characterization.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403
    assert "_addanother" not in body and "add_id_plantings" not in body


def test_the_characterization_list_searches_by_plot_code_and_farm(client):
    mine = PlotCharacterizationFactory(plot__code="P-BUSCADA")
    PlotCharacterizationFactory(plot__code="P-OTRA")

    body = client.get(
        reverse("admin:crops_plotcharacterization_changelist"), {"q": "P-BUSCADA"}
    ).content.decode()

    assert str(mine.plot.code) in body and "P-OTRA" not in body


def test_staff_who_is_not_the_technical_account_does_not_read_characterizations():
    characterization = PlotCharacterizationFactory()
    employee = login(
        UserFactory(
            is_staff=True,
            producer=characterization.plot.farm.producer,
            permissions=["plots.view_plot", "crops.change_plotcharacterization"],
        )
    )

    assert employee.get(reverse("admin:crops_plotcharacterization_changelist")).status_code == 403


def test_the_variety_history_is_read_only_and_only_for_the_superuser(client, superuser):
    create_variety(superuser, {"name": "CCN-51 Alta", "description": ""})
    event = CacaoVarietyAuditEvent.objects.get()
    url = reverse("admin:crops_cacaovarietyauditevent_change", args=[event.pk])

    assert client.get(reverse("admin:crops_cacaovarietyauditevent_changelist")).status_code == 200
    assert "CCN-51 Alta" in client.get(url).content.decode()
    assert client.get(reverse("admin:crops_cacaovarietyauditevent_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    deletion = reverse("admin:crops_cacaovarietyauditevent_delete", args=[event.pk])
    assert client.post(deletion, {"post": "yes"}).status_code == 403

    manager = login(UserFactory(is_staff=True, permissions=["crops.manage_cacaovariety"]))
    assert manager.get(reverse("admin:crops_cacaovarietyauditevent_changelist")).status_code == 403
