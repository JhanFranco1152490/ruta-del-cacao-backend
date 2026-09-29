import uuid
from decimal import Decimal
from types import MappingProxyType

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.common import territorial
from apps.farms import services
from apps.farms.exceptions import (
    DuplicateFarmName,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    MunicipalityDepartmentMismatch,
    ProducerRequired,
    StaleFarmVersion,
)
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.services import create_farm, get_farm, list_farms, update_farm
from apps.farms.tests.factories import FarmFactory, farm_data
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def stranger():
    return UserFactory(producer=ProducerFactory())


def audit_actions(farm):
    return list(
        FarmAuditEvent.objects.filter(farm=farm)
        .order_by("occurred_at")
        .values_list("action", "changed_fields")
    )


# --- Crear -------------------------------------------------------------------------------


def test_create_links_the_farm_to_the_session_producer_and_audits_it(owner):
    farm, created = create_farm(owner, farm_data())

    assert created is True
    assert farm.producer_id == owner.producer_id
    assert farm.version == 1
    assert farm.is_active is True
    assert farm.name_normalized == "la esperanza"
    event = FarmAuditEvent.objects.get(farm=farm)
    assert (event.action, event.actor) == (FarmAuditEvent.Action.CREATED, owner)


def test_create_uses_the_client_id_when_given(owner):
    client_id = uuid.uuid4()

    farm, _ = create_farm(owner, farm_data(id=client_id))

    assert farm.id == client_id


def test_create_generates_an_id_when_the_client_does_not_send_one(owner):
    farm, _ = create_farm(owner, farm_data())

    assert isinstance(farm.id, uuid.UUID)


def test_create_trims_the_name(owner):
    farm, _ = create_farm(owner, farm_data(name="  La Esperanza  "))

    assert farm.name == "La Esperanza"


def test_resending_the_same_id_and_content_returns_the_existing_farm(owner):
    client_id = uuid.uuid4()
    first, _ = create_farm(owner, farm_data(id=client_id))

    again, created = create_farm(owner, farm_data(id=client_id, area_hectares=Decimal("12.5")))

    assert created is False
    assert again.pk == first.pk
    assert Farm.objects.count() == 1
    assert len(audit_actions(first)) == 1


def test_resending_the_same_id_with_other_content_is_a_conflict(owner):
    client_id = uuid.uuid4()
    create_farm(owner, farm_data(id=client_id))

    with pytest.raises(FarmIdConflict):
        create_farm(owner, farm_data(id=client_id, altitude_masl=951))


def test_an_id_that_belongs_to_another_producer_is_a_conflict(owner, stranger):
    client_id = uuid.uuid4()
    create_farm(stranger, farm_data(id=client_id))

    with pytest.raises(FarmIdConflict):
        create_farm(owner, farm_data(id=client_id))

    assert Farm.objects.get(pk=client_id).producer_id == stranger.producer_id


def test_create_rejects_a_normalized_duplicate_name(owner):
    create_farm(owner, farm_data(name="La Esperanza"))

    with pytest.raises(DuplicateFarmName):
        create_farm(owner, farm_data(name=" la esperanza "))

    assert Farm.objects.count() == 1


def test_another_producer_can_use_the_same_name(owner, stranger):
    create_farm(owner, farm_data(name="La Esperanza"))

    farm, _ = create_farm(stranger, farm_data(name="La Esperanza"))

    assert farm.producer_id == stranger.producer_id


@pytest.mark.parametrize(
    "overrides",
    [
        {"latitude": Decimal("90.0000001")},
        {"latitude": Decimal("-90.0000001")},
        {"longitude": Decimal("180.0000001")},
        {"longitude": Decimal("-180.0000001")},
    ],
)
def test_create_rejects_out_of_range_coordinates(owner, overrides):
    with pytest.raises(InvalidCoordinates):
        create_farm(owner, farm_data(**overrides))

    assert not Farm.objects.exists()


def test_create_rejects_a_municipality_from_another_department(owner, monkeypatch):
    monkeypatch.setattr(
        territorial,
        "DEPARTMENTS_BY_CODE",
        MappingProxyType(
            {**territorial.DEPARTMENTS_BY_CODE, "05": territorial.Department("05", "Antioquia")}
        ),
    )
    monkeypatch.setattr(
        territorial,
        "MUNICIPALITIES_BY_CODE",
        MappingProxyType(
            {
                **territorial.MUNICIPALITIES_BY_CODE,
                "05001": territorial.Municipality("05001", "Medellín", "05"),
            }
        ),
    )

    with pytest.raises(MunicipalityDepartmentMismatch):
        create_farm(owner, farm_data(department_code="54", municipality_code="05001"))

    assert not Farm.objects.exists()


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"name": "   "}, "name"),
        ({"department_code": "99"}, "department_code"),
        ({"municipality_code": "99999"}, "municipality_code"),
        ({"area_hectares": Decimal("0")}, "area_hectares"),
        ({"altitude_masl": 9001}, "altitude_masl"),
    ],
)
def test_create_rejects_invalid_fields(owner, overrides, field):
    with pytest.raises(ValidationError) as error:
        create_farm(owner, farm_data(**overrides))

    assert field in error.value.message_dict
    assert not Farm.objects.exists()


def test_an_account_without_producer_cannot_create_farms():
    with pytest.raises(ProducerRequired):
        create_farm(UserFactory(), farm_data())


def test_a_failing_audit_rolls_back_the_creation(owner, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(services.farms, "record_farm_audit_event", fail)

    with pytest.raises(RuntimeError):
        create_farm(owner, farm_data())

    assert not Farm.objects.exists()


# --- Consultar ---------------------------------------------------------------------------


def test_get_returns_an_own_farm(owner):
    farm = FarmFactory(producer=owner.producer)

    assert get_farm(owner, farm.id) == farm


def test_get_hides_a_farm_of_another_producer(owner, stranger):
    farm = FarmFactory(producer=stranger.producer)

    with pytest.raises(FarmNotFound):
        get_farm(owner, farm.id)


def test_get_of_an_unknown_farm_raises(owner):
    with pytest.raises(FarmNotFound):
        get_farm(owner, uuid.uuid4())


def test_list_only_returns_own_farms_ordered_by_name(owner, stranger):
    FarmFactory(producer=owner.producer, name="Zapatoca")
    FarmFactory(producer=owner.producer, name="el Arrayán")
    FarmFactory(producer=stranger.producer, name="Ajena")

    names = [farm.name for farm in list_farms(owner)]

    assert names == ["el Arrayán", "Zapatoca"]


def test_list_of_an_account_without_producer_is_empty():
    FarmFactory()

    assert list(list_farms(UserFactory())) == []


@pytest.mark.parametrize("search", ["arrayan", "ARRAYÁN", "portico", "cucuta"])
def test_list_searches_name_details_and_municipality_ignoring_accents(owner, search):
    FarmFactory(
        producer=owner.producer,
        name="El Arrayán",
        details="Vereda El Pórtico",
        municipality_code="54001",
    )
    FarmFactory(producer=owner.producer, name="Otra", municipality_code="54498")

    names = [farm.name for farm in list_farms(owner, search=search)]

    assert names == ["El Arrayán"]


def test_blank_search_does_not_filter(owner):
    FarmFactory(producer=owner.producer)

    assert len(list(list_farms(owner, search="  "))) == 1


# --- Editar ------------------------------------------------------------------------------


def test_update_changes_the_given_fields_bumps_version_and_audits(owner):
    farm, _ = create_farm(owner, farm_data())

    updated = update_farm(
        owner, farm.id, 1, {"name": "La Nueva Esperanza", "latitude": Decimal("7.1")}
    )

    assert updated.name == "La Nueva Esperanza"
    assert updated.name_normalized == "la nueva esperanza"
    assert updated.latitude == Decimal("7.1")
    assert updated.version == 2
    assert audit_actions(farm)[-1] == (FarmAuditEvent.Action.UPDATED, ["latitude", "name"])


def test_update_without_real_changes_keeps_version_and_does_not_audit(owner):
    farm, _ = create_farm(owner, farm_data())

    updated = update_farm(owner, farm.id, 1, {"name": " La Esperanza ", "altitude_masl": 950})

    assert updated.version == 1
    assert len(audit_actions(farm)) == 1


def test_update_with_a_stale_version_keeps_the_server_data(owner):
    farm, _ = create_farm(owner, farm_data())
    update_farm(owner, farm.id, 1, {"altitude_masl": 1000})

    with pytest.raises(StaleFarmVersion) as error:
        update_farm(owner, farm.id, 1, {"altitude_masl": 1200})

    assert error.value.current_farm.version == 2
    farm.refresh_from_db()
    assert (farm.altitude_masl, farm.version) == (1000, 2)


def test_update_hides_a_farm_of_another_producer(owner, stranger):
    farm = FarmFactory(producer=stranger.producer)

    with pytest.raises(FarmNotFound):
        update_farm(owner, farm.id, 1, {"name": "Mía"})

    farm.refresh_from_db()
    assert farm.name != "Mía"


def test_update_rejects_a_duplicate_name(owner):
    create_farm(owner, farm_data(name="La Esperanza"))
    other, _ = create_farm(owner, farm_data(name="El Porvenir"))

    with pytest.raises(DuplicateFarmName):
        update_farm(owner, other.id, 1, {"name": "LA ESPERANZA"})


def test_update_rejects_out_of_range_coordinates(owner):
    farm, _ = create_farm(owner, farm_data())

    with pytest.raises(InvalidCoordinates):
        update_farm(owner, farm.id, 1, {"longitude": Decimal("-181")})

    farm.refresh_from_db()
    assert farm.version == 1


def test_deactivating_and_reactivating_is_audited_as_a_status_change(owner):
    farm, _ = create_farm(owner, farm_data())

    inactive = update_farm(owner, farm.id, 1, {"is_active": False})
    active = update_farm(owner, farm.id, 2, {"is_active": True})

    assert inactive.is_active is False
    assert active.is_active is True
    assert active.version == 3
    assert audit_actions(farm)[1:] == [
        (FarmAuditEvent.Action.STATUS_CHANGED, ["is_active"]),
        (FarmAuditEvent.Action.STATUS_CHANGED, ["is_active"]),
    ]


def test_editing_data_and_status_together_records_both_events(owner):
    farm, _ = create_farm(owner, farm_data())

    update_farm(owner, farm.id, 1, {"is_active": False, "details": "km 5"})

    assert sorted(audit_actions(farm)[1:]) == sorted(
        [
            (FarmAuditEvent.Action.UPDATED, ["details"]),
            (FarmAuditEvent.Action.STATUS_CHANGED, ["is_active"]),
        ]
    )
