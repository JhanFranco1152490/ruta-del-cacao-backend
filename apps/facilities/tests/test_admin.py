import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_producer_owner
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.facilities.services import create_facility, update_facility
from apps.farms.tests.factories import FarmFactory

from .factories import PostharvestFacilityFactory, facility_data

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


def facility_url(name, facility):
    return reverse(f"admin:facilities_postharvestfacility_{name}", args=[facility.pk])


def facility_form(facility, **overrides):
    data = {
        "facility_type": facility.facility_type,
        "name": facility.name,
        "capacity_kg": facility.capacity_kg,
        "is_active": "on" if facility.is_active else "",
        "expected_version": facility.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


# --- Elementos ---


def test_the_list_and_the_record_open(client):
    facility = PostharvestFacilityFactory(name="C-02")

    listed = client.get(reverse("admin:facilities_postharvestfacility_changelist"))

    assert "C-02" in listed.content.decode()
    assert client.get(facility_url("change", facility)).status_code == 200


def test_the_list_searches_by_name(client):
    PostharvestFacilityFactory(name="C-02")
    PostharvestFacilityFactory(name="Marquesina del patio")

    found = client.get(reverse("admin:facilities_postharvestfacility_changelist"), {"q": "patio"})

    assert "Marquesina del patio" in found.content.decode()
    assert "C-02" not in found.content.decode()


def test_saving_goes_through_the_service_and_the_history_names_the_admin(client, superuser):
    facility = PostharvestFacilityFactory(name="C-02")

    response = client.post(facility_url("change", facility), facility_form(facility, name="C-20"))

    assert response.status_code == 302
    facility.refresh_from_db()
    assert (facility.name, facility.version) == ("C-20", 2)
    event = PostharvestFacilityAuditEvent.objects.get(facility=facility, action="updated")
    assert event.actor == superuser


def test_deactivating_is_a_status_change_in_the_history(client):
    facility = PostharvestFacilityFactory()

    client.post(facility_url("change", facility), facility_form(facility, is_active=""))

    facility.refresh_from_db()
    assert not facility.is_active
    assert PostharvestFacilityAuditEvent.objects.filter(
        facility=facility, action="status_changed"
    ).exists()


def test_the_farm_cannot_be_changed_from_the_form(client):
    facility = PostharvestFacilityFactory()
    farm_id = facility.farm_id

    client.post(
        facility_url("change", facility),
        facility_form(facility, name="C-30", farm=FarmFactory(producer=facility.farm.producer).pk),
    )

    facility.refresh_from_db()
    assert (facility.name, facility.farm_id) == ("C-30", farm_id)


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    facility = PostharvestFacilityFactory(name="C-02")
    stale = facility_form(facility, name="Tardío")
    PostharvestFacility.objects.filter(pk=facility.pk).update(version=2)

    response = client.post(facility_url("change", facility), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    facility.refresh_from_db()
    assert (facility.name, facility.version) == ("C-02", 2)


def test_a_repeated_name_is_refused_with_the_services_message(client):
    facility = PostharvestFacilityFactory(name="C-02")
    PostharvestFacilityFactory(farm=facility.farm, name="C-03")

    response = client.post(
        facility_url("change", facility), facility_form(facility, name="c 03"), follow=True
    )

    assert (
        "Ya existe un elemento con este nombre o código en la finca." in response.content.decode()
    )
    facility.refresh_from_db()
    assert facility.name == "C-02"


def test_the_type_of_a_used_facility_is_refused_with_the_services_message(client, used_facility):
    response = client.post(
        facility_url("change", used_facility),
        facility_form(used_facility, facility_type="solar_dryer"),
        follow=True,
    )

    assert "No se puede cambiar: el elemento ya se usó en un proceso." in response.content.decode()
    used_facility.refresh_from_db()
    assert used_facility.facility_type == "fermentation_box"


def test_deleting_goes_through_the_service(client):
    facility = PostharvestFacilityFactory()

    response = client.post(facility_url("delete", facility), {"post": "yes"})

    assert response.status_code == 302
    assert not PostharvestFacility.objects.filter(pk=facility.pk).exists()
    assert PostharvestFacilityAuditEvent.objects.filter(
        facility_ref=facility.pk, action="deleted"
    ).exists()


def test_a_used_facility_is_not_deleted_and_the_reason_is_shown(client, used_facility):
    response = client.post(facility_url("delete", used_facility), {"post": "yes"}, follow=True)

    assert "Desactívalo" in response.content.decode()
    assert PostharvestFacility.objects.filter(pk=used_facility.pk).exists()


def test_facilities_are_not_added_from_the_admin(client):
    response = client.get(reverse("admin:facilities_postharvestfacility_add"))

    assert response.status_code == 403


# --- Historial ---


@pytest.fixture
def event():
    farm = FarmFactory()
    owner = make_producer_owner(farm.producer)
    facility = create_facility(owner, facility_data(farm, name="C-02"))
    update_facility(owner, facility.pk, 1, {"name": "C-20"})
    return PostharvestFacilityAuditEvent.objects.get(action="updated")


def test_a_superuser_reads_the_history_with_its_values(client, event):
    detail = client.get(
        reverse("admin:facilities_postharvestfacilityauditevent_change", args=[event.pk])
    )

    assert detail.status_code == 200
    assert "C-20" in detail.content.decode()


def test_staff_with_the_api_permission_does_not_read_the_history(event):
    staff = login(UserFactory(is_staff=True, permissions=["facilities.view_postharvestfacility"]))

    response = staff.get(reverse("admin:facilities_postharvestfacilityauditevent_changelist"))

    assert response.status_code == 403


def test_the_history_cannot_be_changed_from_the_admin(client, event):
    delete = client.post(
        reverse("admin:facilities_postharvestfacilityauditevent_delete", args=[event.pk]),
        {"post": "yes"},
    )

    assert delete.status_code == 403
    assert PostharvestFacilityAuditEvent.objects.filter(pk=event.pk).exists()
