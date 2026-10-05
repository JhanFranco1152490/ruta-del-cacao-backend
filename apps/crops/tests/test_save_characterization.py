import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import mock

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_delegate
from apps.crops.exceptions import (
    DensityTooHigh,
    FarmInactive,
    PlotInactive,
    PlotNotFound,
    StaleCharacterizationVersion,
    UnknownVariety,
    VarietyInactive,
)
from apps.crops.models import (
    PlotCharacterization,
    PlotCharacterizationAuditEvent,
    PlotPlanting,
)
from apps.crops.services import save_characterization
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

Action = PlotCharacterizationAuditEvent.Action


@pytest.fixture
def owner():
    return UserFactory(producer=ProducerFactory())


@pytest.fixture
def plot(owner):
    return PlotFactory(farm__producer=owner.producer)


@pytest.fixture
def ccn51():
    return CacaoVarietyFactory(name="CCN-51")


@pytest.fixture
def ics95():
    return CacaoVarietyFactory(name="ICS-95")


MARCH_2021 = date(2021, 3, 1)


def data(*rows, **overrides) -> dict:
    """Una ficha válida como la deja el serializer: siembras de `(variedad, árboles)` o
    `(variedad, árboles, fecha)`; sin fecha, marzo de 2021."""
    content = {
        "plantings": [
            {
                "variety_id": row[0].pk,
                "planting_date": row[2] if len(row) > 2 else MARCH_2021,
                "tree_count": row[1],
            }
            for row in rows
        ],
        "stage": "full_production",
        "management_system": "conventional",
        "shade_type": None,
        "captured_at": None,
    }
    content.update(overrides)
    return content


def rows_of(characterization) -> set:
    return set(characterization.plantings.values_list("variety__name", "tree_count"))


def events_of(plot):
    return PlotCharacterizationAuditEvent.objects.filter(plot=plot)


# --- Registrar ----------------------------------------------------------------------------------


def test_registers_the_characterization_of_a_plot(owner, plot, ccn51, ics95):
    characterization, created = save_characterization(
        owner, plot.pk, None, data((ccn51, 1800), (ics95, 600))
    )

    assert created is True
    characterization.refresh_from_db()
    assert characterization.pk == plot.pk
    assert characterization.version == 1
    assert rows_of(characterization) == {("CCN-51", 1800), ("ICS-95", 600)}
    assert set(characterization.plantings.values_list("planting_date", flat=True)) == {MARCH_2021}
    assert (characterization.stage, characterization.management_system) == (
        "full_production",
        "conventional",
    )
    assert characterization.shade_type is None


def test_registering_leaves_a_created_event_with_the_values(owner, plot, ccn51, ics95):
    save_characterization(owner, plot.pk, None, data((ics95, 600), (ccn51, 1800)))

    event = events_of(plot).get()
    assert event.action == Action.CREATED
    assert event.actor == owner
    assert event.snapshot == {
        "plantings": [
            {
                "variety_id": str(ccn51.pk),
                "name": "CCN-51",
                "planting_date": "2021-03",
                "tree_count": 1800,
            },
            {
                "variety_id": str(ics95.pk),
                "name": "ICS-95",
                "planting_date": "2021-03",
                "tree_count": 600,
            },
        ],
        "stage": "full_production",
        "management_system": "conventional",
        "shade_type": None,
    }


def test_the_device_time_is_kept(owner, plot, ccn51):
    captured_at = datetime(2026, 10, 3, 14, 10, tzinfo=timezone.utc)

    characterization, _ = save_characterization(
        owner, plot.pk, None, data((ccn51, 900), captured_at=captured_at)
    )

    characterization.refresh_from_db()
    assert characterization.captured_at == captured_at


def test_an_employee_with_the_delegated_permission_works_on_the_producers_plot(plot, ccn51):
    employee = make_delegate(plot.farm.producer, ["crops.change_plotcharacterization"])

    _, created = save_characterization(employee, plot.pk, None, data((ccn51, 900)))

    assert created is True
    assert events_of(plot).get().actor == employee


# --- Reemplazar ---------------------------------------------------------------------------------


@pytest.fixture
def registered(owner, plot, ccn51, ics95):
    characterization, _ = save_characterization(
        owner, plot.pk, None, data((ccn51, 1800), (ics95, 600))
    )
    return characterization


def test_replaces_the_whole_characterization_and_raises_the_version(
    owner, plot, registered, ccn51
):
    characterization, created = save_characterization(
        owner, plot.pk, 1, data((ccn51, 2000), stage="renovation", management_system=None)
    )

    assert created is False
    characterization.refresh_from_db()
    assert characterization.version == 2
    assert rows_of(characterization) == {("CCN-51", 2000)}
    assert (characterization.stage, characterization.management_system) == ("renovation", None)
    assert PlotPlanting.objects.count() == 1


def test_replacing_leaves_an_updated_event_with_what_changed(owner, plot, registered, ccn51):
    save_characterization(owner, plot.pk, 1, data((ccn51, 2000), stage="renovation"))

    event = events_of(plot).get(action=Action.UPDATED)
    assert event.changed_fields == ["plantings", "stage"]
    assert event.snapshot["stage"] == "renovation"
    assert event.snapshot["plantings"] == [
        {
            "variety_id": str(ccn51.pk),
            "name": "CCN-51",
            "planting_date": "2021-03",
            "tree_count": 2000,
        }
    ]


def test_each_version_keeps_its_own_values(owner, plot, registered, ccn51, ics95):
    save_characterization(owner, plot.pk, 1, data((ccn51, 1800), (ics95, 600), stage="renovation"))
    save_characterization(
        owner, plot.pk, 2, data((ccn51, 1800), (ics95, 600), stage="establishment")
    )
    save_characterization(
        owner, plot.pk, 3, data((ccn51, 1800), (ics95, 600), stage="early_production")
    )

    # Por versión y no por hora: varios eventos seguidos pueden quedar con la misma hora.
    stages = sorted(
        (event.snapshot["stage"], event.action, event.actor_id) for event in events_of(plot)
    )
    assert stages == sorted(
        [
            ("full_production", Action.CREATED, owner.pk),
            ("renovation", Action.UPDATED, owner.pk),
            ("establishment", Action.UPDATED, owner.pk),
            ("early_production", Action.UPDATED, owner.pk),
        ]
    )
    assert all(event.occurred_at is not None for event in events_of(plot))


# --- Versión y reintentos -----------------------------------------------------------------------


def test_registering_when_it_already_exists_is_stale(owner, plot, registered, ccn51):
    with pytest.raises(StaleCharacterizationVersion) as error:
        save_characterization(owner, plot.pk, None, data((ccn51, 5)))

    assert error.value.current_characterization == registered
    registered.refresh_from_db()
    assert registered.version == 1


def test_an_old_version_is_stale_and_nothing_is_overwritten(owner, plot, registered, ccn51):
    save_characterization(owner, plot.pk, 1, data((ccn51, 2000)))

    with pytest.raises(StaleCharacterizationVersion) as error:
        save_characterization(owner, plot.pk, 1, data((ccn51, 3000)))

    assert error.value.current_characterization.version == 2
    assert rows_of(PlotCharacterization.objects.get(pk=plot.pk)) == {("CCN-51", 2000)}


def test_editing_a_characterization_that_does_not_exist_is_stale_without_current(
    owner, plot, ccn51
):
    with pytest.raises(StaleCharacterizationVersion) as error:
        save_characterization(owner, plot.pk, 1, data((ccn51, 900)))

    assert error.value.current_characterization is None
    assert not PlotCharacterization.objects.exists()


@pytest.mark.parametrize("expected_version", [None, 1, 7], ids=["null", "current", "unknown"])
def test_a_retry_with_the_same_content_succeeds_without_changes(
    owner, plot, registered, ccn51, ics95, expected_version
):
    # Las filas en otro orden y otra hora del dispositivo: siguen siendo la misma ficha.
    retry = data(
        (ics95, 600),
        (ccn51, 1800),
        captured_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )

    characterization, created = save_characterization(owner, plot.pk, expected_version, retry)

    assert created is False
    characterization.refresh_from_db()
    assert characterization.version == 1
    assert characterization.captured_at is None
    assert events_of(plot).count() == 1


# --- Variedades ---------------------------------------------------------------------------------


def test_an_unknown_variety_is_a_validation_error_of_the_plantings(owner, plot, ccn51):
    missing = {"variety_id": uuid.uuid4(), "planting_date": MARCH_2021, "tree_count": 10}
    content = data((ccn51, 900))
    content["plantings"].append(missing)

    with pytest.raises(UnknownVariety) as error:
        save_characterization(owner, plot.pk, None, content)

    assert error.value.status_code == 400
    assert error.value.default_code == "validation_error"
    assert "plantings" in error.value.fields
    assert not PlotCharacterization.objects.exists()


def test_an_inactive_variety_cannot_be_added(owner, plot, ccn51):
    retired = CacaoVarietyFactory(name="EET-8", is_active=False)

    with pytest.raises(VarietyInactive) as error:
        save_characterization(owner, plot.pk, None, data((ccn51, 900), (retired, 10)))

    assert "EET-8" in error.value.fields["plantings"][0]
    assert not PlotCharacterization.objects.exists()


def test_an_inactive_variety_already_in_the_characterization_is_kept_and_corrected(
    owner, plot, registered, ccn51, ics95
):
    ics95.is_active = False
    ics95.save()

    characterization, _ = save_characterization(
        owner, plot.pk, 1, data((ccn51, 1800), (ics95, 650), stage="renovation")
    )

    assert rows_of(characterization) == {("CCN-51", 1800), ("ICS-95", 650)}


def test_an_inactive_variety_is_rejected_in_another_plot(owner, plot, registered, ics95):
    ics95.is_active = False
    ics95.save()
    other = PlotFactory(farm=plot.farm)

    with pytest.raises(VarietyInactive):
        save_characterization(owner, other.pk, None, data((ics95, 10)))


# --- Parcela, finca y alcance -------------------------------------------------------------------


def test_a_plot_of_another_producer_is_not_found_and_stays_untouched(plot, ccn51):
    stranger = UserFactory(producer=ProducerFactory())

    with pytest.raises(PlotNotFound):
        save_characterization(stranger, plot.pk, None, data((ccn51, 900)))

    assert not PlotCharacterization.objects.exists()


def test_an_unknown_plot_is_not_found(owner, ccn51):
    with pytest.raises(PlotNotFound):
        save_characterization(owner, uuid.uuid4(), None, data((ccn51, 900)))


def test_an_account_without_producer_finds_no_plot(plot, ccn51):
    with pytest.raises(PlotNotFound):
        save_characterization(UserFactory(), plot.pk, None, data((ccn51, 900)))


def test_an_inactive_plot_is_frozen(owner, plot, ccn51):
    plot.is_active = False
    plot.save()

    with pytest.raises(PlotInactive):
        save_characterization(owner, plot.pk, None, data((ccn51, 900)))


def test_an_inactive_farm_is_reported_before_its_inactive_plot(owner, plot, ccn51):
    plot.is_active = False
    plot.save()
    plot.farm.is_active = False
    plot.farm.save()

    with pytest.raises(FarmInactive):
        save_characterization(owner, plot.pk, None, data((ccn51, 900)))


# --- Transacción y datos ------------------------------------------------------------------------


def test_nothing_is_saved_if_the_history_fails(owner, plot, registered, ccn51):
    with (
        mock.patch.object(PlotCharacterizationAuditEvent, "record", side_effect=RuntimeError),
        pytest.raises(RuntimeError),
    ):
        save_characterization(owner, plot.pk, 1, data((ccn51, 4000), stage="renovation"))

    registered.refresh_from_db()
    assert registered.version == 1
    assert rows_of(registered) == {("CCN-51", 1800), ("ICS-95", 600)}
    assert events_of(plot).count() == 1


def test_the_snapshot_has_no_personal_data(owner, plot, ccn51):
    save_characterization(owner, plot.pk, None, data((ccn51, 900)))

    snapshot = events_of(plot).get().snapshot
    assert set(snapshot) == {"plantings", "stage", "management_system", "shade_type"}
    assert set(snapshot["plantings"][0]) == {"variety_id", "name", "planting_date", "tree_count"}
    text = str(snapshot)
    for personal in (owner.email, plot.farm.producer.first_name, plot.farm.name, plot.code):
        assert personal not in text


# --- Siembras y densidad ------------------------------------------------------------------------


def test_the_same_variety_is_kept_as_two_plantings_of_different_months(owner, plot, ccn51):
    characterization, _ = save_characterization(
        owner,
        plot.pk,
        None,
        data((ccn51, 1000, date(2018, 4, 1)), (ccn51, 500, date(2024, 2, 1))),
    )

    assert sorted(characterization.plantings.values_list("planting_date", "tree_count")) == [
        (date(2018, 4, 1), 1000),
        (date(2024, 2, 1), 500),
    ]


def test_changing_only_the_date_of_a_planting_is_a_change(owner, plot, registered, ccn51, ics95):
    characterization, _ = save_characterization(
        owner, plot.pk, 1, data((ccn51, 1800, date(2019, 6, 1)), (ics95, 600))
    )

    assert characterization.version == 2
    assert events_of(plot).get(action=Action.UPDATED).changed_fields == ["plantings"]


def test_a_new_planting_of_a_deactivated_variety_the_plot_already_has_is_accepted(
    owner, plot, ccn51
):
    save_characterization(owner, plot.pk, None, data((ccn51, 900)))
    ccn51.is_active = False
    ccn51.save()

    characterization, _ = save_characterization(
        owner, plot.pk, 1, data((ccn51, 900), (ccn51, 300, date(2025, 1, 1)))
    )

    assert characterization.version == 2


def test_an_impossible_density_is_rejected_and_nothing_is_saved(owner, ccn51):
    plot = PlotFactory(farm__producer=owner.producer, area_hectares=Decimal("1.00"))

    with pytest.raises(DensityTooHigh) as error:
        save_characterization(owner, plot.pk, None, data((ccn51, 10_001)))

    assert "10.001 árboles/ha" in error.value.fields["plantings"][0]
    assert not PlotCharacterization.objects.exists()
    assert not events_of(plot).exists()
