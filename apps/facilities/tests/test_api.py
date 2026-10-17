import pytest

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import grant_role, make_administrator, make_producer_owner
from apps.facilities.models import PostharvestFacility, PostharvestFacilityAuditEvent
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestFacilityFactory, facility_data

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


# --- Registrar ---


def body(farm, **overrides) -> dict:
    data = facility_data(farm, **overrides)
    data["farm_id"] = str(data["farm_id"])
    return data


def test_registering_needs_a_session_and_the_permission(anonymous_client, auth_client, farm):
    assert anonymous_client.post(URL, body(farm), format="json").status_code == 401
    assert (
        auth_client(make_administrator()).post(URL, body(farm), format="json").status_code == 403
    )


def test_the_producer_registers_an_available_facility(auth_client, owner, farm):
    response = auth_client(owner).post(URL, body(farm), format="json")

    assert response.status_code == 201
    assert response["Location"].endswith(f"{URL}/{response.data['id']}")
    assert (response.data["name"], response.data["status"], response.data["farm"]["id"]) == (
        "C-04",
        "available",
        str(farm.pk),
    )
    assert PostharvestFacilityAuditEvent.objects.filter(action="created").count() == 1


def test_the_foreman_registers_in_its_farm(auth_client, foreman, farm):
    assert auth_client(foreman).post(URL, body(farm), format="json").status_code == 201


@pytest.mark.parametrize("missing", ["farm_id", "facility_type", "name", "capacity_kg"])
def test_every_field_is_required(auth_client, owner, farm, missing):
    data = body(farm)
    del data[missing]

    response = auth_client(owner).post(URL, data, format="json")

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert missing in response.data["fields"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("facility_type", "mechanical_dryer"),
        ("name", "   "),
        ("name", "x" * 41),
        ("capacity_kg", 0),
        ("capacity_kg", 10_001),
        ("capacity_kg", "600.5"),
    ],
)
def test_invalid_values_are_rejected_in_their_field(auth_client, owner, farm, field, value):
    response = auth_client(owner).post(URL, body(farm, **{field: value}), format="json")

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert field in response.data["fields"]
    assert PostharvestFacility.objects.count() == 0


def test_an_unknown_field_is_rejected(auth_client, owner, farm):
    response = auth_client(owner).post(URL, body(farm, is_active=False), format="json")

    assert response.status_code == 400
    assert "is_active" in response.data["fields"]


def test_a_repeated_name_answers_with_the_existing_facility(auth_client, owner, farm):
    existing = PostharvestFacilityFactory(farm=farm, name="C-02", is_active=False)

    response = auth_client(owner).post(URL, body(farm, name="c-02"), format="json")

    assert (response.status_code, response.data["code"]) == (409, "duplicate_facility_name")
    assert response.data["existing"] == {
        "id": str(existing.pk),
        "name": "C-02",
        "facility_type": "fermentation_box",
        "is_active": False,
    }
    assert "name" in response.data["fields"]


def test_an_inactive_farm_is_rejected(auth_client, owner, producer):
    farm = FarmFactory(producer=producer, is_active=False)

    response = auth_client(owner).post(URL, body(farm), format="json")

    assert (response.status_code, response.data["code"]) == (422, "farm_inactive")


def test_a_farm_of_another_producer_is_not_found(auth_client, owner):
    response = auth_client(owner).post(URL, body(FarmFactory()), format="json")

    assert (response.status_code, response.data["code"]) == (404, "not_found")


def test_a_name_with_only_dashes_is_a_validation_error_in_its_field(auth_client, owner, farm):
    response = auth_client(owner).post(URL, body(farm, name=" - "), format="json")

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert "name" in response.data["fields"]


# --- Editar, activar y desactivar ---


def patch(client, facility, **data):
    return client.patch(detail(facility), data, format="json")


def test_editing_needs_the_permission(auth_client, box):
    response = patch(auth_client(make_administrator()), box, expected_version=1, name="C-9")

    assert response.status_code == 403


def test_the_foreman_edits_and_deactivates(auth_client, foreman, box):
    client = auth_client(foreman)

    edited = patch(client, box, expected_version=1, name="C-20", capacity_kg=700)
    deactivated = patch(client, box, expected_version=2, is_active=False)

    assert (edited.status_code, edited.data["name"], edited.data["capacity_kg"]) == (
        200,
        "C-20",
        700,
    )
    assert (deactivated.data["status"], deactivated.data["version"]) == ("inactive", 3)


def test_the_farm_cannot_be_changed(auth_client, owner, producer, box):
    other = FarmFactory(producer=producer)

    response = patch(auth_client(owner), box, expected_version=1, farm_id=str(other.pk))

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert "farm_id" in response.data["fields"]
    box.refresh_from_db()
    assert box.farm_id != other.pk


def test_the_version_is_required(auth_client, owner, box):
    response = patch(auth_client(owner), box, name="C-9")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_a_patch_with_only_the_version_is_rejected(auth_client, owner, box):
    assert patch(auth_client(owner), box, expected_version=1).status_code == 400


def test_a_stale_version_answers_with_the_current_facility(auth_client, owner, box):
    client = auth_client(owner)
    patch(client, box, expected_version=1, capacity_kg=650)

    response = patch(client, box, expected_version=1, capacity_kg=700)

    assert (response.status_code, response.data["code"]) == (409, "stale_version")
    assert response.data["current"]["capacity_kg"] == 650


def test_the_type_of_a_used_facility_is_locked_in_the_api(auth_client, used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    response = patch(
        auth_client(owner), used_facility, expected_version=1, facility_type="solar_dryer"
    )

    assert (response.status_code, response.data["code"]) == (422, "facility_fields_locked")
    assert "facility_type" in response.data["fields"]


def test_a_repeated_name_answers_with_the_existing_one_when_editing(auth_client, owner, farm, box):
    existing = PostharvestFacilityFactory(farm=farm, name="C-07")

    response = patch(auth_client(owner), box, expected_version=1, name="c 07")

    assert (response.status_code, response.data["code"]) == (409, "duplicate_facility_name")
    assert response.data["existing"]["id"] == str(existing.pk)


# --- Eliminar ---


def test_deleting_is_only_for_the_producer_by_default(auth_client, foreman, box):
    response = auth_client(foreman).delete(f"{detail(box)}?expected_version=1")

    assert response.status_code == 403


def test_the_producer_deletes_a_facility_never_used(auth_client, owner, box):
    response = auth_client(owner).delete(f"{detail(box)}?expected_version=1")

    assert response.status_code == 204
    assert not PostharvestFacility.objects.filter(pk=box.pk).exists()


def test_deleting_needs_the_version(auth_client, owner, box):
    response = auth_client(owner).delete(detail(box))

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_a_used_facility_answers_that_it_has_records(auth_client, used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    response = auth_client(owner).delete(f"{detail(used_facility)}?expected_version=1")

    assert (response.status_code, response.data["code"]) == (409, "facility_has_records")


def test_a_used_facility_is_listed_with_its_records(auth_client, used_facility):
    owner = make_producer_owner(used_facility.farm.producer)

    assert auth_client(owner).get(detail(used_facility)).data["has_records"] is True
