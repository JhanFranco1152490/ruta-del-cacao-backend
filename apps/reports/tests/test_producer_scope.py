import uuid
from datetime import date

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.reports.exceptions import ReportFilterNotFound, ReportTypeNotAllowed
from apps.reports.report import ReportFilter

from .helpers import PERIOD, Estate, generate, harvest, lot_of

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


def not_found_field(error):
    return set(error.value.fields)


def test_the_report_says_its_type_who_generated_it_and_when(estate):
    estate.owner.first_name, estate.owner.last_name = "Rosa", "Quintero"
    estate.owner.save()
    before = timezone.now()

    report = generate(estate.owner, type="production", **PERIOD)

    assert (report.type, report.title) == ("production", "Producción")
    assert report.generated_by == "Rosa Quintero"
    assert before <= report.generated_at <= timezone.now()
    assert report.filters == (
        ReportFilter(key="period", label="Periodo", text="01/01/2026 – 31/03/2026"),
    )


def test_the_filters_are_named_with_codes_and_names(estate):
    lot = lot_of(estate.rio)

    report = generate(
        estate.owner,
        type="production",
        **PERIOD,
        farm=str(estate.esperanza.pk),
        plot=str(estate.rio.pk),
        lot=str(lot.pk),
    )

    assert report.filters[1:] == (
        ReportFilter(key="farm", label="Finca", text="F01 · La Esperanza", id=estate.esperanza.pk),
        ReportFilter(
            key="plot", label="Parcela", text=f"{estate.rio.code} · El Río", id=estate.rio.pk
        ),
        ReportFilter(key="lot", label="Lote", text=lot.code, id=lot.pk),
    )


def test_the_inventory_has_no_period_filter(estate):
    report = generate(estate.owner, type="inventory")

    assert report.filters == ()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("farm", lambda estate: estate.other_farm.pk),
        ("farm", lambda estate: uuid.uuid4()),
        ("plot", lambda estate: estate.other_plot.pk),
        ("lot", lambda estate: lot_of(estate.other_plot).pk),
    ],
)
def test_a_filter_outside_the_producer_is_not_found(estate, field, value):
    with pytest.raises(ReportFilterNotFound) as error:
        generate(estate.owner, type="production", **PERIOD, **{field: str(value(estate))})

    assert error.value.status_code == 404
    assert not_found_field(error) == {field}


def test_a_plot_of_another_of_its_farms_does_not_match_the_farm(estate):
    with pytest.raises(ReportFilterNotFound) as error:
        generate(
            estate.owner,
            type="production",
            **PERIOD,
            farm=str(estate.esperanza.pk),
            plot=str(estate.alto.pk),
        )

    assert not_found_field(error) == {"plot"}


def test_a_lot_of_another_plot_does_not_match_the_plot(estate):
    lot = lot_of(estate.loma)

    with pytest.raises(ReportFilterNotFound) as error:
        generate(
            estate.owner, type="production", **PERIOD, plot=str(estate.rio.pk), lot=str(lot.pk)
        )

    assert not_found_field(error) == {"lot"}


@pytest.mark.parametrize(
    ("report_type", "module_permission"),
    [
        ("production", "harvests.view_harvest"),
        ("quality", "lots.view_lot"),
        ("inventory", "warehouse.view_stock"),
    ],
)
def test_each_type_asks_for_the_permission_of_its_module(estate, report_type, module_permission):
    without = estate.employee(farm=estate.esperanza)
    with_it = estate.employee(module_permission, farm=estate.esperanza)
    period = {} if report_type == "inventory" else PERIOD

    with pytest.raises(ReportTypeNotAllowed) as error:
        generate(without, type=report_type, **period)
    assert error.value.status_code == 403
    assert generate(with_it, type=report_type, **period).type == report_type


def test_an_employee_reaches_only_its_farm(estate):
    harvest(estate.rio, date(2026, 2, 1), "10.0")
    harvest(estate.alto, date(2026, 2, 1), "20.0")
    employee = estate.employee("harvests.view_harvest", farm=estate.esperanza)

    report = generate(employee, type="production", **PERIOD)

    assert [row["farm"] for row in report.rows] == ["F01 · La Esperanza"]
    with pytest.raises(ReportFilterNotFound):
        generate(employee, type="production", **PERIOD, farm=str(estate.mirador.pk))


def test_a_producer_cannot_choose_another_producer(estate):
    harvest(estate.other_plot, date(2026, 2, 1), "10.0")

    report = generate(
        estate.owner,
        type="production",
        **PERIOD,
        producer=str(estate.other_farm.producer_id),
    )

    assert report.rows == []
    assert [item.key for item in report.filters] == ["period"]


def test_the_technical_account_chooses_a_producer(estate):
    harvest(estate.rio, date(2026, 2, 1), "10.0")
    harvest(estate.other_plot, date(2026, 2, 1), "20.0")
    technical = UserFactory(is_superuser=True)

    everything = generate(technical, type="production", **PERIOD)
    one = generate(technical, type="production", **PERIOD, producer=str(estate.producer.pk))

    assert len(everything.rows) == 2
    assert [row["farm"] for row in one.rows] == ["F01 · La Esperanza"]
    assert one.filters[1].key == "producer"
    producer = estate.producer
    assert one.filters[1].text == (
        f"{producer.member_code} · {producer.first_name} {producer.last_name}"
    )


def test_the_technical_account_and_a_producer_without_farms(estate):
    technical = UserFactory(is_superuser=True)

    with pytest.raises(ReportFilterNotFound) as error:
        generate(technical, type="production", **PERIOD, producer=str(uuid.uuid4()))

    assert not_found_field(error) == {"producer"}
