import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.common import territorial
from apps.farms import services
from apps.farms.exceptions import (
    DuplicateFarmName,
    FarmHasRecords,
    FarmIdConflict,
    FarmNotFound,
    InvalidCoordinates,
    LocationOutsideOperatingArea,
    MunicipalityDepartmentMismatch,
    ProducerRequired,
    StaleFarmVersion,
)
from apps.farms.models import Farm, FarmAuditEvent
from apps.farms.services import create_farm, delete_farm, get_farm, list_farms, update_farm
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


def test_create_keeps_the_device_capture_time_as_given(owner):
    captured_at = datetime(2026, 9, 20, 7, 30, tzinfo=UTC)

    farm, _ = create_farm(owner, farm_data(captured_at=captured_at))

    farm.refresh_from_db()
    assert farm.captured_at == captured_at


def test_capture_time_is_optional(owner):
    farm, _ = create_farm(owner, farm_data())

    assert farm.captured_at is None


def test_a_resent_farm_is_not_rejected_for_its_capture_time(owner):
    # Es informativo: un reintento no se vuelve conflicto por la hora del dispositivo.
    client_id = uuid.uuid4()
    first, _ = create_farm(
        owner, farm_data(id=client_id, captured_at=datetime(2026, 9, 20, tzinfo=UTC))
    )

    again, created = create_farm(owner, farm_data(id=client_id))

    assert (again.pk, created) == (first.pk, False)


def test_resending_the_same_id_and_content_returns_the_existing_farm(owner):
    client_id = uuid.uuid4()
    first, _ = create_farm(owner, farm_data(id=client_id))

    again, created = create_farm(owner, farm_data(id=client_id, area_hectares=Decimal("12.5")))

    assert created is False
    assert again.pk == first.pk
    assert Farm.objects.count() == 1
    assert len(audit_actions(first)) == 1


def test_resending_the_same_id_with_other_content_is_a_conflict_with_the_server_farm(owner):
    # La creación se aplicó pero la respuesta se perdió, y el pendiente se editó en el
    # dispositivo: el conflicto trae la finca del servidor para continuar con un PATCH.
    client_id = uuid.uuid4()
    create_farm(owner, farm_data(id=client_id))

    with pytest.raises(FarmIdConflict) as error:
        create_farm(owner, farm_data(id=client_id, altitude_masl=951))

    assert error.value.current_farm.pk == client_id
    assert error.value.current_farm.altitude_masl == 950


def test_an_id_that_belongs_to_another_producer_is_a_conflict_without_its_data(owner, stranger):
    client_id = uuid.uuid4()
    create_farm(stranger, farm_data(id=client_id))

    with pytest.raises(FarmIdConflict) as error:
        create_farm(owner, farm_data(id=client_id))

    assert error.value.current_farm is None
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


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"latitude": Decimal("6.8719999")}, "latitude"),
        ({"latitude": Decimal("9.2910001")}, "latitude"),
        ({"longitude": Decimal("-73.6340001")}, "longitude"),
        ({"longitude": Decimal("-72.0469999")}, "longitude"),
    ],
)
def test_create_rejects_a_point_outside_norte_de_santander(owner, overrides, field):
    with pytest.raises(LocationOutsideOperatingArea) as error:
        create_farm(owner, farm_data(**overrides))

    assert list(error.value.fields) == [field]
    assert not Farm.objects.exists()


def test_create_accepts_a_point_on_the_border_of_the_operating_area(owner):
    farm, _ = create_farm(
        owner, farm_data(latitude=Decimal("6.872"), longitude=Decimal("-73.634"))
    )

    assert (farm.latitude, farm.longitude) == (Decimal("6.872"), Decimal("-73.634"))


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


def test_list_shows_active_farms_first_and_then_inactive_ones(owner):
    # El orden lo da el servidor: la lista viene paginada y el cliente no puede reordenarla.
    FarmFactory(producer=owner.producer, name="Arrayán", is_active=False)
    FarmFactory(producer=owner.producer, name="Zapatoca")
    FarmFactory(producer=owner.producer, name="Bellavista")
    FarmFactory(producer=owner.producer, name="Altamira", is_active=False)

    names = [farm.name for farm in list_farms(owner)]

    assert names == ["Bellavista", "Zapatoca", "Altamira", "Arrayán"]


def test_list_of_an_account_without_producer_is_empty():
    FarmFactory()

    assert list(list_farms(UserFactory())) == []


@pytest.mark.parametrize(
    "search, expected",
    [
        ("arrayan", ["El Arrayán"]),
        ("ARRAYÁN", ["El Arrayán"]),
        # Solo el nombre: el municipio tiene su propio filtro y los detalles no se buscan.
        ("portico", []),
        ("cucuta", []),
    ],
)
def test_list_searches_only_the_name_ignoring_accents(owner, search, expected):
    FarmFactory(
        producer=owner.producer,
        name="El Arrayán",
        details="Vereda El Pórtico",
        municipality_code="54001",
    )
    FarmFactory(producer=owner.producer, name="Otra", municipality_code="54498")

    names = [farm.name for farm in list_farms(owner, search=search)]

    assert names == expected


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


def test_retrying_an_already_applied_update_succeeds_without_changes(owner):
    # La respuesta del primer envío se perdió: la cola reintenta con la versión que tenía.
    farm, _ = create_farm(owner, farm_data())
    update_farm(owner, farm.id, 1, {"name": "El Porvenir", "altitude_masl": 1000})

    retried = update_farm(owner, farm.id, 1, {"name": " El Porvenir ", "altitude_masl": 1000})

    assert (retried.name, retried.altitude_masl, retried.version) == ("El Porvenir", 1000, 2)
    assert len(audit_actions(farm)) == 2


def test_a_stale_update_that_only_partly_matches_is_still_a_conflict(owner):
    farm, _ = create_farm(owner, farm_data())
    update_farm(owner, farm.id, 1, {"altitude_masl": 1000})

    with pytest.raises(StaleFarmVersion):
        update_farm(owner, farm.id, 1, {"altitude_masl": 1000, "name": "Otra"})


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


def test_update_rejects_moving_the_point_outside_norte_de_santander(owner):
    farm, _ = create_farm(owner, farm_data())

    with pytest.raises(LocationOutsideOperatingArea):
        update_farm(
            owner, farm.id, 1, {"latitude": Decimal("4.6"), "longitude": Decimal("-74.08")}
        )

    farm.refresh_from_db()
    assert (farm.latitude, farm.version) == (Decimal("7.8234567"), 1)


def test_a_farm_already_outside_can_still_edit_its_other_fields(owner):
    # Una finca guardada antes de la regla (o en datos de prueba) no queda bloqueada: solo se
    # valida el rectángulo cuando cambian las coordenadas.
    farm = FarmFactory(
        producer=owner.producer, latitude=Decimal("4.6"), longitude=Decimal("-74.08")
    )

    updated = update_farm(owner, farm.id, 1, {"name": "Otro nombre", "latitude": Decimal("4.6")})

    assert (updated.name, updated.version) == ("Otro nombre", 2)


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


# --- Eliminar ----------------------------------------------------------------------------


def test_deleting_a_farm_keeps_its_audit_and_records_the_deletion(owner):
    farm, _ = create_farm(owner, farm_data(name="Creada por error"))
    update_farm(owner, farm.id, 1, {"altitude_masl": 1000})
    farm_id = farm.id

    delete_farm(owner, farm_id, 2)

    assert not Farm.objects.filter(pk=farm_id).exists()
    events = FarmAuditEvent.objects.filter(farm_ref=farm_id).order_by("occurred_at")
    assert [event.action for event in events] == [
        FarmAuditEvent.Action.CREATED,
        FarmAuditEvent.Action.UPDATED,
        FarmAuditEvent.Action.DELETED,
    ]
    assert all(event.farm is None for event in events)
    assert {event.farm_name for event in events} == {"Creada por error"}
    assert events.last().actor == owner


def test_a_farm_with_business_records_cannot_be_deleted(owner, farm_dependent_model):
    farm, _ = create_farm(owner, farm_data())
    farm_dependent_model.objects.create(farm=farm)

    with pytest.raises(FarmHasRecords):
        delete_farm(owner, farm.id, 1)

    assert Farm.objects.filter(pk=farm.id).exists()
    assert not FarmAuditEvent.objects.filter(action=FarmAuditEvent.Action.DELETED).exists()


def test_deleting_with_a_stale_version_keeps_the_farm(owner):
    farm, _ = create_farm(owner, farm_data())
    update_farm(owner, farm.id, 1, {"altitude_masl": 1000})

    with pytest.raises(StaleFarmVersion) as error:
        delete_farm(owner, farm.id, 1)

    assert error.value.current_farm.version == 2
    assert Farm.objects.filter(pk=farm.id).exists()


def test_deleting_a_farm_of_another_producer_is_not_found(owner, stranger):
    farm = FarmFactory(producer=stranger.producer)

    with pytest.raises(FarmNotFound):
        delete_farm(owner, farm.id, 1)

    assert Farm.objects.filter(pk=farm.id).exists()


def test_a_failing_audit_rolls_back_the_deletion(owner, monkeypatch):
    farm, _ = create_farm(owner, farm_data())

    def fail(**kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(services.farms, "record_farm_audit_event", fail)

    with pytest.raises(RuntimeError):
        delete_farm(owner, farm.id, 1)

    assert Farm.objects.filter(pk=farm.id).exists()
