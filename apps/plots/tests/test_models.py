from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.tests.factories import UserFactory
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import Plot, PlotAuditEvent
from apps.plots.services.audit import record_plot_audit_event
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db

BOUNDARY = [
    {"latitude": "7.8000000", "longitude": "-72.5000000", "source": "map"},
    {"latitude": "7.8000000", "longitude": "-72.4990000", "source": "map"},
    {"latitude": "7.8010000", "longitude": "-72.4990000", "source": "map"},
]


def test_code_is_unique_within_a_farm_after_normalization():
    plot = PlotFactory(code="P-01")

    with pytest.raises(IntegrityError), transaction.atomic():
        PlotFactory(farm=plot.farm, code=" p-01 ")


def test_the_same_code_can_be_used_in_another_farm():
    plot = PlotFactory(code="P-01")

    PlotFactory(farm=FarmFactory(producer=plot.farm.producer), code="P-01")


def test_area_must_be_positive():
    with pytest.raises(IntegrityError), transaction.atomic():
        PlotFactory(area_hectares=Decimal("0"))


@pytest.mark.parametrize(
    ("boundary", "measured"),
    [(BOUNDARY, None), (None, Decimal("1.2250"))],
    ids=["boundary_alone", "area_alone"],
)
def test_boundary_and_measured_area_go_together(boundary, measured):
    with pytest.raises(IntegrityError), transaction.atomic():
        PlotFactory(boundary=boundary, measured_area_hectares=measured)


def test_a_plot_without_boundary_has_no_measured_area():
    plot = PlotFactory()

    plot.refresh_from_db()
    assert (plot.boundary, plot.measured_area_hectares) == (None, None)


def test_a_plot_keeps_its_boundary_and_measured_area():
    plot = PlotFactory(boundary=BOUNDARY, measured_area_hectares=Decimal("0.6125"))

    plot.refresh_from_db()
    assert plot.boundary == BOUNDARY
    assert plot.measured_area_hectares == Decimal("0.6125")


def test_clean_trims_and_normalizes_the_code():
    plot = Plot(code="  P-01 · El Mango ", area_hectares=Decimal("1.00"))

    plot.clean()

    assert plot.code == "P-01 · El Mango"
    assert plot.code_normalized == "p-01 · el mango"


@pytest.mark.parametrize("code", ["", "   "])
def test_clean_requires_a_code(code):
    with pytest.raises(ValidationError) as error:
        Plot(code=code, area_hectares=Decimal("1.00")).clean()

    assert "code" in error.value.message_dict


def test_a_farm_with_plots_cannot_be_deleted():
    plot = PlotFactory()

    with pytest.raises(ProtectedError):
        plot.farm.delete()


def test_audit_event_keeps_both_areas_after_the_change():
    plot = PlotFactory(boundary=BOUNDARY, measured_area_hectares=Decimal("0.6125"))

    event = record_plot_audit_event(
        plot=plot,
        actor=UserFactory(),
        action=PlotAuditEvent.Action.UPDATED,
        changed_fields=["boundary", "area_hectares"],
    )

    event.refresh_from_db()
    assert event.changed_fields == ["area_hectares", "boundary"]
    # La copia del id y del código identifica a la parcela aunque después se elimine.
    assert (event.plot_ref, event.plot_code) == (plot.pk, plot.code)
    assert (event.area_hectares, event.measured_area_hectares) == (
        Decimal("1.00"),
        Decimal("0.6125"),
    )


def test_plot_permissions_are_named_in_spanish_for_the_role_editor():
    names = dict(
        Permission.objects.filter(
            content_type__app_label="plots", content_type__model="plot"
        ).values_list("codename", "name")
    )

    assert names == {
        "view_plot": "Puede consultar parcelas",
        "add_plot": "Puede registrar parcelas",
        "change_plot": "Puede editar, activar y desactivar parcelas",
        "delete_plot": "Puede eliminar parcelas creadas por error",
    }
