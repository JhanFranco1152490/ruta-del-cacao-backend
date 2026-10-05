import uuid
from datetime import UTC, date, datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.crops.models import PlotCharacterization, PlotCharacterizationAuditEvent
from apps.crops.tests.factories import (
    CacaoVarietyFactory,
    PlotCharacterizationFactory,
    PlotCharacterizationVarietyFactory,
)
from apps.farms.tests.factories import FarmFactory
from apps.plots.tests.factories import PlotFactory
from apps.producers.tests.factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/plot-characterizations"
SELECT_VARIETY = "Seleccione la variedad de cacao."


def detail_url(plot) -> str:
    return f"{URL}/{plot.pk}"


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def client(auth_client, owner):
    return auth_client(owner)


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def plot(farm):
    return PlotFactory(farm=farm)


@pytest.fixture
def ccn51():
    return CacaoVarietyFactory(name="CCN-51")


@pytest.fixture
def ics95():
    return CacaoVarietyFactory(name="ICS-95")


def body(*rows, **overrides) -> dict:
    content = {
        "expected_version": None,
        "varieties": [
            {"variety_id": str(variety.pk), "tree_count": tree_count}
            for variety, tree_count in rows
        ],
        "planting_date": "2021-03",
        "stage": "full_production",
        "management_system": "conventional",
        "shade_type": None,
        "captured_at": "2026-10-03T14:10:00Z",
    }
    content.update(overrides)
    return content


def characterize(plot, *rows, **fields):
    characterization = PlotCharacterizationFactory(plot=plot, **fields)
    for variety, tree_count in rows:
        PlotCharacterizationVarietyFactory(
            characterization=characterization, variety=variety, tree_count=tree_count
        )
    return characterization


def month_after(day: date) -> str:
    year, month = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
    return f"{year:04d}-{month:02d}"


# --- Registrar y reemplazar ---------------------------------------------------------------------


def test_registering_a_characterization_responds_201_with_it(client, plot, ccn51, ics95):
    response = client.put(detail_url(plot), body((ccn51, 1800), (ics95, 600)), format="json")

    assert response.status_code == 201
    assert response["Location"].endswith(detail_url(plot))
    data = response.data
    assert data["plot_id"] == str(plot.pk)
    assert data["varieties"] == [
        {
            "variety": {"id": str(ccn51.pk), "name": "CCN-51", "is_active": True},
            "tree_count": 1800,
        },
        {
            "variety": {"id": str(ics95.pk), "name": "ICS-95", "is_active": True},
            "tree_count": 600,
        },
    ]
    assert data["total_trees"] == 2400
    assert data["planting_date"] == "2021-03"
    assert (data["stage"], data["management_system"], data["shade_type"]) == (
        "full_production",
        "conventional",
        None,
    )
    assert data["version"] == 1
    # La API responde en la zona horaria del proyecto: se compara el instante, no el texto.
    assert parse_datetime(data["captured_at"]) == datetime(2026, 10, 3, 14, 10, tzinfo=UTC)
    assert {"created_at", "updated_at"} <= set(data)
    assert PlotCharacterizationAuditEvent.objects.filter(plot=plot).count() == 1


def test_replacing_responds_200_with_the_new_version(client, plot, ccn51):
    characterize(plot, (ccn51, 900))

    response = client.put(
        detail_url(plot),
        body((ccn51, 1200), expected_version=1, stage="renovation"),
        format="json",
    )

    assert response.status_code == 200
    assert response.data["version"] == 2
    assert response.data["total_trees"] == 1200
    assert response.data["stage"] == "renovation"


def test_a_retry_with_the_same_content_responds_200_without_a_new_version(client, plot, ccn51):
    first = client.put(detail_url(plot), body((ccn51, 900)), format="json")

    retry = client.put(detail_url(plot), body((ccn51, 900)), format="json")

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.data["version"] == 1


def test_an_old_version_is_stale_with_the_current_characterization(client, plot, ccn51):
    characterize(plot, (ccn51, 900), version=2)

    response = client.put(detail_url(plot), body((ccn51, 1000), expected_version=1), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"]["version"] == 2
    assert response.data["current"]["total_trees"] == 900


def test_editing_a_missing_characterization_is_stale_with_null_current(client, plot, ccn51):
    response = client.put(detail_url(plot), body((ccn51, 900), expected_version=1), format="json")

    assert response.status_code == 409
    assert response.data["code"] == "stale_version"
    assert response.data["current"] is None


def test_management_and_shade_are_optional(client, plot, ccn51):
    content = body((ccn51, 900))
    del content["management_system"], content["shade_type"], content["captured_at"]

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == 201
    assert (response.data["management_system"], response.data["shade_type"]) == (None, None)
    assert response.data["captured_at"] is None


# --- Validaciones del cuerpo --------------------------------------------------------------------


@pytest.mark.parametrize("varieties", [[], None, "missing"], ids=["empty_list", "null", "missing"])
def test_without_varieties_asks_to_select_one(client, plot, varieties):
    content = body(varieties=varieties)
    if varieties == "missing":
        del content["varieties"]

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert response.data["fields"]["varieties"] == [SELECT_VARIETY]
    assert not PlotCharacterization.objects.exists()


def test_ten_varieties_are_accepted_and_eleven_are_not(client, plot):
    varieties = CacaoVarietyFactory.create_batch(11)

    ten = client.put(
        detail_url(plot), body(*[(variety, 10) for variety in varieties[:10]]), format="json"
    )
    eleven = client.put(
        detail_url(PlotFactory(farm=plot.farm)),
        body(*[(variety, 10) for variety in varieties]),
        format="json",
    )

    assert ten.status_code == 201
    assert ten.data["total_trees"] == 100
    assert eleven.status_code == 400
    assert "varieties" in eleven.data["fields"]


def test_a_repeated_variety_is_rejected(client, plot, ccn51):
    response = client.put(detail_url(plot), body((ccn51, 10), (ccn51, 20)), format="json")

    assert response.status_code == 400
    assert response.data["fields"]["varieties"] == ["Esta variedad ya está en la lista."]


@pytest.mark.parametrize(
    ("tree_count", "status_code"),
    [(0, 400), (1, 201), (1_000_000, 201), (1_000_001, 400), (2.5, 400), ("mil", 400)],
)
def test_tree_count_limits(client, plot, ccn51, tree_count, status_code):
    content = body(varieties=[{"variety_id": str(ccn51.pk), "tree_count": tree_count}])

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == status_code


def test_an_unknown_variety_goes_to_the_varieties_field(client, plot, ccn51):
    content = body((ccn51, 10))
    content["varieties"].append({"variety_id": str(uuid.uuid4()), "tree_count": 5})

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "varieties" in response.data["fields"]


def test_an_inactive_variety_is_unprocessable(client, plot):
    retired = CacaoVarietyFactory(is_active=False)

    response = client.put(detail_url(plot), body((retired, 10)), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "variety_inactive"


@pytest.mark.parametrize(
    "planting_date",
    ["2021-3", "2021-13", "2021-00", "2021-03-01", "marzo", "٢٠٢١-٠٣", "2021-03\n", None, ""],
)
def test_a_malformed_planting_date_is_rejected(client, plot, ccn51, planting_date):
    response = client.put(
        detail_url(plot), body((ccn51, 10), planting_date=planting_date), format="json"
    )

    assert response.status_code == 400
    assert "planting_date" in response.data["fields"]


def test_planting_dates_from_1950_to_this_month_are_accepted(client, farm, ccn51):
    today = timezone.localdate()
    for planting_date in ("1950-01", f"{today.year:04d}-{today.month:02d}"):
        response = client.put(
            detail_url(PlotFactory(farm=farm)),
            body((ccn51, 10), planting_date=planting_date),
            format="json",
        )
        assert response.status_code == 201, planting_date
        assert response.data["planting_date"] == planting_date


@pytest.mark.parametrize("which", ["before_1950", "next_month"])
def test_planting_dates_out_of_range_are_rejected(client, plot, ccn51, which):
    planting_date = "1949-12" if which == "before_1950" else month_after(timezone.localdate())

    response = client.put(
        detail_url(plot), body((ccn51, 10), planting_date=planting_date), format="json"
    )

    assert response.status_code == 400
    assert "planting_date" in response.data["fields"]


def test_the_planting_date_is_stored_on_the_first_of_the_month(client, plot, ccn51):
    client.put(detail_url(plot), body((ccn51, 10), planting_date="2019-11"), format="json")

    assert PlotCharacterization.objects.get().planting_date == date(2019, 11, 1)


@pytest.mark.parametrize(
    "overrides",
    [
        {"stage": None},
        {"stage": "harvest"},
        {"management_system": "traditional"},
        {"shade_type": "partial"},
        {"expected_version": 0},
        {"expected_version": "uno"},
        {"captured_at": "ayer"},
        {"version": 3},
        {"total_trees": 10},
    ],
    ids=[
        "no_stage",
        "unknown_stage",
        "unknown_management",
        "unknown_shade",
        "zero_version",
        "text_version",
        "bad_captured_at",
        "read_only_version",
        "read_only_total",
    ],
)
def test_invalid_bodies_are_rejected(client, plot, ccn51, overrides):
    response = client.put(detail_url(plot), body((ccn51, 10), **overrides), format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert not PlotCharacterization.objects.exists()


def test_expected_version_is_required(client, plot, ccn51):
    content = body((ccn51, 10))
    del content["expected_version"]

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == 400
    assert "expected_version" in response.data["fields"]


def test_unknown_fields_in_a_row_are_rejected(client, plot, ccn51):
    content = body(varieties=[{"variety_id": str(ccn51.pk), "tree_count": 10, "name": "X"}])

    response = client.put(detail_url(plot), content, format="json")

    assert response.status_code == 400


# --- Parcela, finca, permisos y alcance ---------------------------------------------------------


def test_an_inactive_plot_is_unprocessable(client, plot, ccn51):
    plot.is_active = False
    plot.save()

    response = client.put(detail_url(plot), body((ccn51, 10)), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "plot_inactive"


def test_an_inactive_farm_is_unprocessable(client, plot, ccn51):
    plot.farm.is_active = False
    plot.farm.save()

    response = client.put(detail_url(plot), body((ccn51, 10)), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "farm_inactive"


def test_another_producers_plot_is_not_found_for_reading_or_writing(auth_client, plot, ccn51):
    characterize(plot, (ccn51, 900))
    stranger = auth_client(make_producer_owner(ProducerFactory()))

    read = stranger.get(detail_url(plot))
    write = stranger.put(detail_url(plot), body((ccn51, 5), expected_version=1), format="json")

    assert (read.status_code, write.status_code) == (404, 404)
    assert PlotCharacterization.objects.get().version == 1


def test_an_unknown_plot_is_not_found(client, ccn51):
    response = client.put(f"{URL}/{uuid.uuid4()}", body((ccn51, 10)), format="json")

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_saving_requires_a_session(api_client, plot, ccn51):
    assert api_client.put(detail_url(plot), body((ccn51, 10)), format="json").status_code == 401


def test_a_delegate_with_the_permission_saves(auth_client, producer, plot, ccn51):
    employee = auth_client(make_delegate(producer, ["crops.change_plotcharacterization"]))

    response = employee.put(detail_url(plot), body((ccn51, 10)), format="json")

    assert response.status_code == 201


def test_a_delegate_who_only_sees_plots_cannot_save(auth_client, producer, plot, ccn51):
    employee = auth_client(make_delegate(producer, ["plots.view_plot"]))

    response = employee.put(detail_url(plot), body((ccn51, 10)), format="json")

    assert response.status_code == 403
    assert response.data["code"] == "permission_denied"


def test_the_association_does_not_read_characterizations(auth_client, plot, ccn51):
    characterize(plot, (ccn51, 900))
    admin = auth_client(make_administrator())

    assert admin.get(detail_url(plot)).status_code == 403
    assert admin.get(URL, {"farm": str(plot.farm.pk)}).status_code == 403


# --- Consultar ----------------------------------------------------------------------------------


def test_reading_a_characterization(client, plot, ccn51, ics95):
    characterize(plot, (ccn51, 1800), (ics95, 600))

    response = client.get(detail_url(plot))

    assert response.status_code == 200
    assert response.data["total_trees"] == 2400
    assert [row["variety"]["name"] for row in response.data["varieties"]] == ["CCN-51", "ICS-95"]


def test_a_plot_without_characterization_is_not_found(client, plot):
    response = client.get(detail_url(plot))

    assert response.status_code == 404
    assert response.data["code"] == "not_found"


def test_an_inactive_variety_is_shown_as_such(client, plot):
    retired = CacaoVarietyFactory(name="EET-8", is_active=False)
    characterize(plot, (retired, 50))

    response = client.get(detail_url(plot))

    assert response.data["varieties"][0]["variety"] == {
        "id": str(retired.pk),
        "name": "EET-8",
        "is_active": False,
    }


def test_the_list_brings_only_the_characterizations_of_that_farm(client, farm, ccn51):
    first = characterize(PlotFactory(farm=farm, code="P-01"), (ccn51, 10))
    second = characterize(PlotFactory(farm=farm, code="P-02"), (ccn51, 20))
    PlotFactory(farm=farm, code="P-03")
    characterize(PlotFactory(farm=FarmFactory(producer=farm.producer)), (ccn51, 30))

    response = client.get(URL, {"farm": str(farm.pk)})

    assert response.status_code == 200
    assert set(response.data) == {"results"}
    assert [item["plot_id"] for item in response.data["results"]] == [
        str(first.pk),
        str(second.pk),
    ]


def test_the_list_of_another_producers_farm_is_empty(auth_client, farm, ccn51):
    characterize(PlotFactory(farm=farm), (ccn51, 10))
    stranger = auth_client(make_producer_owner(ProducerFactory()))

    response = stranger.get(URL, {"farm": str(farm.pk)})

    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.parametrize(
    "farm_param", [None, "", "no-es-un-uuid"], ids=["missing", "blank", "bad"]
)
def test_the_list_needs_a_valid_farm(client, farm_param):
    params = {} if farm_param is None else {"farm": farm_param}

    response = client.get(URL, params)

    assert response.status_code == 400
    assert "farm" in response.data["fields"]


def test_reading_requires_a_session(api_client, farm):
    assert api_client.get(URL, {"farm": str(farm.pk)}).status_code == 401


def test_a_delegate_who_sees_plots_reads_characterizations(auth_client, producer, plot, ccn51):
    characterize(plot, (ccn51, 10))
    employee = auth_client(make_delegate(producer, ["plots.view_plot"]))

    assert employee.get(detail_url(plot)).status_code == 200


def test_reading_without_seeing_plots_is_forbidden(auth_client, plot):
    response = auth_client(UserFactory(producer=plot.farm.producer)).get(detail_url(plot))

    assert response.status_code == 403


def test_the_list_takes_the_same_queries_with_one_or_many_characterizations(client, farm):
    characterize(PlotFactory(farm=farm), (CacaoVarietyFactory(), 10))
    with CaptureQueriesContext(connection) as one:
        client.get(URL, {"farm": str(farm.pk)})

    for _ in range(4):
        characterize(
            PlotFactory(farm=farm),
            (CacaoVarietyFactory(), 10),
            (CacaoVarietyFactory(), 20),
            (CacaoVarietyFactory(), 30),
        )
    with CaptureQueriesContext(connection) as many:
        response = client.get(URL, {"farm": str(farm.pk)})

    assert len(response.data["results"]) == 5
    assert len(many) == len(one)


def test_a_stale_version_takes_the_same_queries_with_one_or_many_varieties(client, farm, ccn51):
    small = characterize(PlotFactory(farm=farm), (CacaoVarietyFactory(), 10), version=2)
    with CaptureQueriesContext(connection) as one:
        client.put(detail_url(small.plot), body((ccn51, 5), expected_version=1), format="json")

    rows = [(CacaoVarietyFactory(), 10 * n) for n in range(1, 6)]
    large = characterize(PlotFactory(farm=farm), *rows, version=2)
    with CaptureQueriesContext(connection) as many:
        response = client.put(
            detail_url(large.plot), body((ccn51, 5), expected_version=1), format="json"
        )

    assert len(response.data["current"]["varieties"]) == 5
    assert len(many) == len(one)
