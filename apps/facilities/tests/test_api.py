import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_producer_owner
from apps.facilities.models import PostharvestFacility
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestFacilityFactory

pytestmark = pytest.mark.django_db

URL = "/api/postharvest-facilities"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def foreman(producer, farm):
    return grant_role(UserFactory(producer=producer, farm=farm), get_system_role(FOREMAN))


@pytest.fixture
def box(farm):
    return PostharvestFacilityFactory(farm=farm, name="C-02")


def detail(facility) -> str:
    return f"{URL}/{facility.pk}"


# --- Sesión y permisos ---


def test_every_read_needs_a_session(anonymous_client, box):
    assert anonymous_client.get(URL).status_code == 401
    assert anonymous_client.get(detail(box)).status_code == 401


def test_the_association_has_no_access(auth_client, box):
    client = auth_client(make_administrator())

    assert client.get(URL).status_code == 403
    assert client.get(detail(box)).status_code == 403


def test_the_foreman_reads_the_facilities_of_its_farm(auth_client, foreman, box):
    client = auth_client(foreman)

    assert client.get(URL).status_code == 200
    assert client.get(detail(box)).status_code == 200


# --- Consultar ---


def test_the_list_brings_active_and_inactive_facilities_without_paging(auth_client, owner, farm):
    active = PostharvestFacilityFactory(farm=farm, name="C-01")
    inactive = PostharvestFacilityFactory(farm=farm, name="C-03", is_active=False)

    response = auth_client(owner).get(URL)

    assert response.status_code == 200
    assert set(response.data) == {"results"}
    assert [row["id"] for row in response.data["results"]] == [str(active.pk), str(inactive.pk)]


def test_the_list_puts_boxes_first_then_dryers_each_by_name(auth_client, owner, farm):
    dryer = PostharvestFacilityFactory(
        farm=farm, name="M-01", facility_type=PostharvestFacility.FacilityType.SOLAR_DRYER
    )
    second_box = PostharvestFacilityFactory(farm=farm, name="C-02")
    first_box = PostharvestFacilityFactory(farm=farm, name="C-01")

    rows = auth_client(owner).get(URL).data["results"]

    assert [row["id"] for row in rows] == [str(first_box.pk), str(second_box.pk), str(dryer.pk)]


def test_a_facility_is_shown_with_its_farm_status_and_records(auth_client, owner, box):
    response = auth_client(owner).get(detail(box))

    assert response.status_code == 200
    assert response.data == {
        "id": str(box.pk),
        "farm": {"id": str(box.farm.pk), "name": box.farm.name, "is_active": True},
        "producer_id": str(box.farm.producer_id),
        "facility_type": "fermentation_box",
        "name": "C-02",
        "capacity_kg": 600,
        "is_active": True,
        "status": "available",
        "has_records": False,
        "version": 1,
        "created_at": response.data["created_at"],
        "updated_at": response.data["updated_at"],
    }


def test_an_inactive_facility_has_the_inactive_status(auth_client, owner, farm):
    facility = PostharvestFacilityFactory(farm=farm, is_active=False)

    assert auth_client(owner).get(detail(facility)).data["status"] == "inactive"


def test_a_facility_of_another_producer_does_not_exist(auth_client, owner):
    foreign = PostharvestFacilityFactory()

    response = auth_client(owner).get(detail(foreign))

    assert (response.status_code, response.data["code"]) == (404, "not_found")
    assert str(foreign.pk) not in {
        row["id"] for row in auth_client(owner).get(URL).data["results"]
    }


def test_the_technical_account_sees_every_producer_and_can_filter_by_one(auth_client, box):
    other = PostharvestFacilityFactory()
    client = auth_client(UserFactory(is_superuser=True))

    everything = {row["id"] for row in client.get(URL).data["results"]}
    filtered = {
        row["id"]
        for row in client.get(URL, {"producer": str(box.farm.producer_id)}).data["results"]
    }

    assert {str(box.pk), str(other.pk)} <= everything
    assert filtered == {str(box.pk)}


def test_another_account_cannot_choose_a_producer(auth_client, owner, box):
    other = PostharvestFacilityFactory()

    listed = {
        row["id"]
        for row in auth_client(owner)
        .get(URL, {"producer": str(other.farm.producer_id)})
        .data["results"]
    }

    assert listed == {str(box.pk)}


def test_a_malformed_producer_is_a_validation_error(auth_client, owner):
    response = auth_client(owner).get(URL, {"producer": "no-es-un-uuid"})

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
