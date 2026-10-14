import re
from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.farms.models import Farm, FarmAuditEvent
from apps.inputs.tests.factories import InputMovementFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import FarmFactory

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


def changelist_url():
    return reverse("admin:farms_farm_changelist")


def change_url(farm):
    return reverse("admin:farms_farm_change", args=[farm.pk])


def delete_url(farm):
    return reverse("admin:farms_farm_delete", args=[farm.pk])


def form_data(farm, **overrides):
    data = {
        "name": farm.name,
        "municipality_code": farm.municipality_code,
        "details": farm.details,
        "area_hectares": str(farm.area_hectares),
        "altitude_masl": farm.altitude_masl,
        "latitude": str(farm.latitude),
        "longitude": str(farm.longitude),
        "is_active": "on" if farm.is_active else "",
        "expected_version": farm.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


def test_the_list_shows_the_farm_with_its_producer_and_the_area_given_to_plots(client):
    farm = FarmFactory(name="La Esperanza", area_hectares=Decimal("10.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("4.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("3.00"), is_active=False)

    body = client.get(changelist_url()).content.decode()

    assert "La Esperanza" in body
    assert farm.producer.member_code in body
    # Solo cuentan las parcelas activas: 4, no 7.
    allocated = re.search(r'field-allocated_area">([^<]*)<', body).group(1)
    assert allocated.replace(",", ".") == "4.00"


def test_the_list_searches_by_name_without_accents_and_by_producer(client):
    FarmFactory(name="Finca El Pórtico")
    other = FarmFactory(name="Otra finca")

    by_name = client.get(changelist_url(), {"q": "portico"}).content.decode()
    by_producer = client.get(changelist_url(), {"q": other.producer.member_code}).content.decode()

    assert "Finca El Pórtico" in by_name and "Otra finca" not in by_name
    assert "Otra finca" in by_producer and "Finca El Pórtico" not in by_producer


def test_the_change_page_carries_the_version_the_form_was_opened_at(client):
    farm = FarmFactory()

    body = client.get(change_url(farm)).content.decode()

    assert 'name="expected_version"' in body
    assert f'value="{farm.version}"' in body


def test_saving_goes_through_the_service_and_leaves_the_history_with_the_admin_as_actor(
    client, superuser
):
    farm = FarmFactory(name="La Esperanza")

    response = client.post(change_url(farm), form_data(farm, name="La Esperanza Alta"))

    assert response.status_code == 302
    farm.refresh_from_db()
    assert (farm.name, farm.version) == ("La Esperanza Alta", 2)
    event = FarmAuditEvent.objects.get(farm=farm, action=FarmAuditEvent.Action.UPDATED)
    assert event.actor == superuser
    assert event.changed_fields == ["name"]


def test_deactivating_is_a_status_change_in_the_history(client):
    farm = FarmFactory()

    client.post(change_url(farm), form_data(farm, is_active=""))

    farm.refresh_from_db()
    assert not farm.is_active
    assert FarmAuditEvent.objects.filter(
        farm=farm, action=FarmAuditEvent.Action.STATUS_CHANGED
    ).exists()


def test_the_producer_and_the_department_cannot_be_changed_from_the_form(client):
    farm = FarmFactory()
    producer_id = farm.producer_id
    other = ProducerFactory()

    client.post(
        change_url(farm),
        form_data(farm, producer=other.pk, department_code="68", name="Otro nombre"),
    )

    farm.refresh_from_db()
    assert farm.name == "Otro nombre"
    assert (farm.producer_id, farm.department_code) == (producer_id, "54")


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    farm = FarmFactory(name="La Esperanza")
    stale = form_data(farm, name="Cambio tardío")
    Farm.objects.filter(pk=farm.pk).update(version=2)

    response = client.post(change_url(farm), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    farm.refresh_from_db()
    assert (farm.name, farm.version) == ("La Esperanza", 2)


def test_an_area_below_what_the_plots_use_is_refused_with_the_services_message(client):
    farm = FarmFactory(area_hectares=Decimal("10.00"))
    PlotFactory(farm=farm, area_hectares=Decimal("6.00"))

    response = client.post(change_url(farm), form_data(farm, area_hectares="3.00"), follow=True)

    assert "no puede ser menor que la de sus parcelas" in response.content.decode()
    assert response.redirect_chain[-1][0] == change_url(farm)
    farm.refresh_from_db()
    assert (farm.area_hectares, farm.version) == (Decimal("10.00"), 1)


def test_a_repeated_name_is_refused_with_the_services_message(client):
    farm = FarmFactory()
    FarmFactory(producer=farm.producer, name="Ya existe")

    response = client.post(change_url(farm), form_data(farm, name="Ya existe"), follow=True)

    assert "Ya existe una finca con este nombre" in response.content.decode()
    farm.refresh_from_db()
    assert farm.version == 1


def test_nobody_can_add_farms_from_the_admin(client):
    assert client.get(reverse("admin:farms_farm_add")).status_code == 403


def test_a_farm_created_by_mistake_is_deleted_through_the_service_and_leaves_its_trace(
    client, superuser
):
    farm = FarmFactory()

    response = client.post(delete_url(farm), {"post": "yes"})

    assert response.status_code == 302
    assert not Farm.objects.filter(pk=farm.pk).exists()
    event = FarmAuditEvent.objects.get(farm_ref=farm.pk, action=FarmAuditEvent.Action.DELETED)
    assert event.actor == superuser


def test_a_farm_with_records_is_not_deleted_and_the_admin_says_why(client):
    farm = FarmFactory()
    InputMovementFactory(farm=farm, input__producer=farm.producer)

    response = client.post(delete_url(farm), {"post": "yes"}, follow=True)

    assert Farm.objects.filter(pk=farm.pk).exists()
    assert "tiene registros asociados" in response.content.decode()


def test_the_bulk_delete_action_is_not_offered(client):
    FarmFactory()

    assert "delete_selected" not in client.get(changelist_url()).content.decode()


def test_staff_who_is_not_the_technical_account_only_reaches_its_own_producers_farms():
    mine = FarmFactory(name="De mi productor")
    theirs = FarmFactory(name="De otro productor")
    staff = UserFactory(
        is_staff=True,
        producer=mine.producer,
        permissions=["farms.view_farm", "farms.change_farm"],
    )
    client = login(staff)

    body = client.get(changelist_url()).content.decode()

    assert "De mi productor" in body and "De otro productor" not in body
    assert client.get(change_url(theirs)).status_code == 302


def test_viewing_without_the_change_permission_is_read_only():
    farm = FarmFactory()
    staff = UserFactory(is_staff=True, producer=farm.producer, permissions=["farms.view_farm"])
    client = login(staff)

    assert client.get(change_url(farm)).status_code == 200
    assert client.post(change_url(farm), form_data(farm, name="Cambio")).status_code == 403
    farm.refresh_from_db()
    assert farm.version == 1


def test_the_history_is_read_only_and_only_for_the_superuser(client):
    farm = FarmFactory()
    client.post(change_url(farm), form_data(farm, name="Nuevo nombre"))
    event = FarmAuditEvent.objects.get(action=FarmAuditEvent.Action.UPDATED)
    url = reverse("admin:farms_farmauditevent_change", args=[event.pk])

    assert client.get(reverse("admin:farms_farmauditevent_changelist")).status_code == 200
    assert client.get(url).status_code == 200
    assert client.get(reverse("admin:farms_farmauditevent_add")).status_code == 403
    assert client.post(url, {}).status_code == 403
    assert (
        client.post(
            reverse("admin:farms_farmauditevent_delete", args=[event.pk]), {"post": "yes"}
        ).status_code
        == 403
    )

    staff = login(UserFactory(is_staff=True, permissions=["farms.view_farm"]))
    assert staff.get(reverse("admin:farms_farmauditevent_changelist")).status_code == 403
