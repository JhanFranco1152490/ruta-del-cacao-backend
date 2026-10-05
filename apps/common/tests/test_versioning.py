from types import SimpleNamespace

import pytest

from apps.common.versioning import check_expected_version, save_next_version
from apps.farms.models import Farm
from apps.farms.services.farms import NAME_UNIQUE_CONSTRAINT
from apps.farms.tests.factories import FarmFactory

pytestmark = pytest.mark.django_db


class Stale(Exception):
    pass


class NameTaken(Exception):
    pass


def never_asked():
    raise AssertionError("No debía preguntar si el cambio ya estaba aplicado.")


# --- check_expected_version ---------------------------------------------------------------------


def test_a_matching_version_lets_the_edit_continue_without_checking_the_content():
    row = SimpleNamespace(version=3)

    assert check_expected_version(row, 3, stale=Stale, already_applied=never_asked) is False


def test_an_old_version_is_stale():
    row = SimpleNamespace(version=3)

    with pytest.raises(Stale):
        check_expected_version(row, 2, stale=Stale)


def test_an_old_version_is_stale_when_the_content_is_not_there_yet():
    row = SimpleNamespace(version=3)

    with pytest.raises(Stale):
        check_expected_version(row, 2, stale=Stale, already_applied=lambda: False)


def test_an_old_version_is_a_replay_when_the_row_already_has_what_is_asked():
    row = SimpleNamespace(version=3)

    assert check_expected_version(row, 2, stale=Stale, already_applied=lambda: True) is True


def test_the_conflict_error_is_built_only_when_it_is_raised():
    row = SimpleNamespace(version=3)
    built = []

    check_expected_version(row, 3, stale=lambda: built.append("built") or Stale())
    check_expected_version(row, 2, stale=Stale, already_applied=lambda: True)

    assert built == []


# --- save_next_version --------------------------------------------------------------------------


def test_it_raises_the_version_and_writes_only_the_given_fields():
    farm = FarmFactory(details="antes", area_hectares=5)
    farm.details = "después"
    farm.area_hectares = 9

    save_next_version(farm, ["details"], constraint=NAME_UNIQUE_CONSTRAINT, duplicate=NameTaken)

    stored = Farm.objects.get(pk=farm.pk)
    assert farm.version == 2
    assert stored.version == 2
    assert stored.details == "después"
    assert stored.area_hectares == 5


def test_a_name_that_is_already_taken_becomes_the_domain_error():
    first = FarmFactory(name="La Esperanza", name_normalized="la esperanza")
    other = FarmFactory(producer=first.producer, name="El Mirador", name_normalized="el mirador")
    other.name = first.name
    other.name_normalized = first.name_normalized

    with pytest.raises(NameTaken):
        save_next_version(
            other,
            ["name", "name_normalized"],
            constraint=NAME_UNIQUE_CONSTRAINT,
            duplicate=NameTaken,
        )

    assert Farm.objects.get(pk=other.pk).name == "El Mirador"
