from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts.tests.factories import UserFactory
from apps.crops.choices import ManagementSystem, ShadeType, Stage
from apps.crops.models import (
    CacaoVariety,
    CacaoVarietyAuditEvent,
    PlotCharacterizationAuditEvent,
)
from apps.crops.tests.factories import (
    CacaoVarietyFactory,
    PlotCharacterizationFactory,
    PlotPlantingFactory,
)
from apps.plots.tests.factories import PlotFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("repeated", ["abc 12", "ABC12", " ABC-12 ", "ABC–12"])
def test_variety_name_is_unique_after_normalization(repeated):
    CacaoVarietyFactory(name="ABC-12")

    with pytest.raises(IntegrityError), transaction.atomic():
        CacaoVarietyFactory(name=repeated)


def test_clean_trims_and_normalizes_the_name():
    variety = CacaoVariety(name="  ABC – 12 ")

    variety.clean()

    assert variety.name == "ABC – 12"
    assert variety.name_normalized == "abc12"


@pytest.mark.parametrize("name", ["", "   ", " - "])
def test_clean_requires_a_name(name):
    with pytest.raises(ValidationError) as error:
        CacaoVariety(name=name).clean()

    assert "name" in error.value.message_dict


def test_a_variety_is_active_and_without_description_by_default():
    variety = CacaoVarietyFactory()

    variety.refresh_from_db()
    assert (variety.is_active, variety.description) == (True, "")


def test_a_plot_has_a_single_characterization():
    characterization = PlotCharacterizationFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        PlotCharacterizationFactory(plot=characterization.plot)


def test_the_characterization_is_identified_by_its_plot():
    plot = PlotFactory()

    characterization = PlotCharacterizationFactory(plot=plot)

    assert characterization.pk == plot.pk
    assert plot.characterization == characterization


def test_a_new_characterization_starts_at_version_one_without_optional_fields():
    characterization = PlotCharacterizationFactory()

    characterization.refresh_from_db()
    assert characterization.version == 1
    assert (characterization.management_system, characterization.shade_type) == (None, None)
    assert characterization.captured_at is None


def test_planting_date_is_stored_on_the_first_day_of_the_month():
    with pytest.raises(IntegrityError), transaction.atomic():
        PlotPlantingFactory(planting_date=date(2021, 3, 15))


def test_the_same_variety_can_be_planted_on_different_months():
    first = PlotPlantingFactory(planting_date=date(2018, 4, 1))
    PlotPlantingFactory(
        characterization=first.characterization,
        variety=first.variety,
        planting_date=date(2024, 2, 1),
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PlotPlantingFactory(
            characterization=first.characterization,
            variety=first.variety,
            planting_date=date(2024, 2, 1),
        )


@pytest.mark.parametrize("tree_count", [0, -1])
def test_tree_count_must_be_positive(tree_count):
    with pytest.raises(IntegrityError), transaction.atomic():
        PlotPlantingFactory(tree_count=tree_count)


def test_a_variety_appears_once_per_characterization():
    row = PlotPlantingFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        PlotPlantingFactory(characterization=row.characterization, variety=row.variety)


def test_rows_go_away_with_their_characterization():
    row = PlotPlantingFactory()

    row.characterization.delete()

    assert not type(row).objects.filter(pk=row.pk).exists()


def test_a_variety_used_by_a_characterization_cannot_be_deleted():
    row = PlotPlantingFactory()

    with pytest.raises(ProtectedError):
        row.variety.delete()


def test_a_plot_with_a_characterization_cannot_be_deleted():
    characterization = PlotCharacterizationFactory()

    with pytest.raises(ProtectedError):
        characterization.plot.delete()


def test_characterization_audit_event_keeps_the_values_of_the_version():
    characterization = PlotCharacterizationFactory()
    snapshot = {"plantings": [{"name": "CCN-51", "tree_count": 9, "stage": "full_production"}]}

    event = PlotCharacterizationAuditEvent.record(
        plot=characterization.plot,
        actor=UserFactory(),
        action=PlotCharacterizationAuditEvent.Action.CREATED,
        version=1,
        snapshot=snapshot,
    )

    event.refresh_from_db()
    assert event.snapshot == snapshot
    assert event.version == 1
    assert event.plot == characterization.plot


def test_a_plot_with_characterization_history_cannot_be_deleted():
    plot = PlotFactory()
    PlotCharacterizationAuditEvent.record(
        plot=plot,
        actor=None,
        action=PlotCharacterizationAuditEvent.Action.UPDATED,
        version=2,
        snapshot={},
    )

    with pytest.raises(ProtectedError):
        plot.delete()


def test_variety_history_survives_the_deletion_of_the_variety():
    variety = CacaoVarietyFactory(name="ABC-12")
    event = CacaoVarietyAuditEvent.record(
        variety=variety,
        variety_ref=variety.pk,
        variety_name=variety.name,
        actor=UserFactory(),
        action=CacaoVarietyAuditEvent.Action.DELETED,
    )
    variety_id = variety.pk

    variety.delete()

    event.refresh_from_db()
    assert event.variety is None
    assert (event.variety_ref, event.variety_name) == (variety_id, "ABC-12")


def test_crops_declare_only_the_permissions_something_checks():
    names = dict(
        Permission.objects.filter(content_type__app_label="crops").values_list("codename", "name")
    )

    assert names == {
        "manage_cacaovariety": "Puede registrar, editar, activar y desactivar variedades de cacao",
        "change_plotcharacterization": "Puede registrar y editar la caracterización de parcelas",
    }


def test_choice_values_are_the_ones_the_client_sends():
    assert Stage.values == [
        "establishment",
        "early_production",
        "full_production",
        "renovation",
    ]
    assert ManagementSystem.values == ["conventional", "organic", "in_transition"]
    assert ShadeType.values == ["none", "temporary", "permanent", "mixed"]
