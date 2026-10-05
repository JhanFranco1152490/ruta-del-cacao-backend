import pytest
from django.db import IntegrityError

from apps.accounts.tests.factories import UserFactory
from apps.common.db import has_dependent_rows
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import record_farm_audit_event
from apps.farms.tests.factories import FarmFactory
from apps.plots.models import PlotAuditEvent
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


def test_a_row_without_dependents_has_none():
    assert has_dependent_rows(FarmFactory()) is False


@pytest.mark.parametrize("is_active", [True, False])
def test_any_row_pointing_to_it_counts_active_or_not(is_active):
    plot = PlotFactory(is_active=is_active)

    assert has_dependent_rows(plot.farm) is True


def test_the_ignored_tables_do_not_count():
    farm = FarmFactory()
    record_farm_audit_event(farm=farm, actor=UserFactory(), action=FarmAuditEvent.Action.CREATED)

    assert has_dependent_rows(farm) is True
    assert has_dependent_rows(farm, ignore=(FarmAuditEvent,)) is False


def test_a_plot_with_only_its_history_has_no_dependents():
    plot = PlotFactory()
    PlotAuditEvent.record(
        plot=plot,
        plot_ref=plot.pk,
        plot_code=plot.code,
        actor=UserFactory(),
        action=PlotAuditEvent.Action.CREATED,
        area_hectares=plot.area_hectares,
    )

    assert has_dependent_rows(plot, ignore=(PlotAuditEvent,)) is False


# --- save_translating_unique --------------------------------------------------------------------

from apps.common.db import save_translating_unique  # noqa: E402
from apps.farms.models import Farm  # noqa: E402
from apps.farms.services.farms import NAME_UNIQUE_CONSTRAINT  # noqa: E402
from apps.producers.tests.factories import ProducerFactory  # noqa: E402


class NameTaken(Exception):
    pass


def new_farm(producer, name):
    return FarmFactory.build(producer=producer, name=name, name_normalized=name.lower())


def test_a_free_name_is_saved_and_nothing_is_returned():
    farm = new_farm(ProducerFactory(), "La Esperanza")

    found = save_translating_unique(
        lambda: farm.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=NameTaken,
    )

    assert found is None
    assert Farm.objects.filter(pk=farm.pk).exists()


def test_a_name_that_already_exists_becomes_the_domain_error():
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="La Esperanza", name_normalized="la esperanza")
    farm = new_farm(producer, "La Esperanza")

    with pytest.raises(NameTaken):
        save_translating_unique(
            lambda: farm.save(force_insert=True),
            constraint=NAME_UNIQUE_CONSTRAINT,
            duplicate=NameTaken,
        )


def test_the_transaction_stays_usable_after_the_clash():
    # El choque ocurre en un punto de guardado propio: no deja rota la transacción de quien llama.
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="La Esperanza", name_normalized="la esperanza")
    farm = new_farm(producer, "La Esperanza")

    with pytest.raises(NameTaken):
        save_translating_unique(
            lambda: farm.save(force_insert=True),
            constraint=NAME_UNIQUE_CONSTRAINT,
            duplicate=NameTaken,
        )

    assert Farm.objects.count() == 1


def test_a_clash_on_another_constraint_is_not_hidden():
    farm = FarmFactory()
    clone = new_farm(farm.producer, "Otra")
    clone.pk = farm.pk

    with pytest.raises(IntegrityError):
        save_translating_unique(
            lambda: clone.save(force_insert=True),
            constraint=NAME_UNIQUE_CONSTRAINT,
            duplicate=NameTaken,
        )


def test_a_record_that_won_the_race_is_returned_before_looking_at_the_name():
    # Un reenvío trae el mismo id y el mismo nombre: PostgreSQL puede reportar el choque en
    # cualquiera de las dos restricciones, así que se mira primero si el id ya existe.
    existing = FarmFactory(name="La Esperanza", name_normalized="la esperanza")
    resent = new_farm(existing.producer, "La Esperanza")
    resent.pk = existing.pk

    found = save_translating_unique(
        lambda: resent.save(force_insert=True),
        constraint=NAME_UNIQUE_CONSTRAINT,
        duplicate=NameTaken,
        find_existing=lambda: Farm.objects.filter(pk=resent.pk).first(),
    )

    assert found == existing


def test_without_a_record_to_find_the_clash_is_still_translated():
    producer = ProducerFactory()
    FarmFactory(producer=producer, name="La Esperanza", name_normalized="la esperanza")
    farm = new_farm(producer, "La Esperanza")

    with pytest.raises(NameTaken):
        save_translating_unique(
            lambda: farm.save(force_insert=True),
            constraint=NAME_UNIQUE_CONSTRAINT,
            duplicate=NameTaken,
            find_existing=lambda: None,
        )
