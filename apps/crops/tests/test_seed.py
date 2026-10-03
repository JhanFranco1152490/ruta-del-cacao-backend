from importlib import import_module

import pytest
from django.apps import apps as installed_apps

from apps.crops.models import CacaoVariety
from apps.crops.text import normalize_variety_name

pytestmark = pytest.mark.django_db

# Las pruebas con `transaction=True` vacían las tablas al terminar, también las que llenó una
# migración, así que se llama a la función de la migración en vez de confiar en lo que dejó.
seed = import_module("apps.crops.migrations.0002_seed_cacao_varieties")

EXPECTED_NAMES = {
    "CCN-51",
    "EET-8",
    "EET-96",
    "EET-400",
    "ICS-1",
    "ICS-6",
    "ICS-39",
    "ICS-40",
    "ICS-60",
    "ICS-95",
    "TSH-565",
    "TSH-812",
    "UF-650",
    "CAU-39",
    "CAU-43",
    "FEAR-5",
    "FLE-2",
    "FLE-3",
    "FSA-11",
    "FSA-12",
    "FSA-13",
    "FTA-2",
    "SCC-61",
    "TCS-01",
    "TCS-06",
    "TCS-13",
    "TCS-19",
    "Híbrido o común (sin identificar)",
}


@pytest.fixture
def seeded():
    CacaoVariety.objects.all().delete()
    seed.add_initial_varieties(installed_apps, None)


def test_the_initial_catalog_has_the_authorized_clones_and_the_unknown_option(seeded):
    varieties = CacaoVariety.objects.all()

    assert {variety.name for variety in varieties} == EXPECTED_NAMES
    assert all(variety.is_active for variety in varieties)


def test_each_initial_variety_is_stored_with_its_normalized_name(seeded):
    for variety in CacaoVariety.objects.all():
        assert variety.name_normalized == normalize_variety_name(variety.name)


def test_the_description_tells_origin_and_compatibility(seeded):
    ccn51 = CacaoVariety.objects.get(name="CCN-51")
    fear5 = CacaoVariety.objects.get(name="FEAR-5")
    tcs01 = CacaoVariety.objects.get(name="TCS-01")

    assert ccn51.description == "Procedencia: Ecuador. Autocompatible."
    assert fear5.description == "Procedencia: Colombia (Fedecacao, Arauquita). Autocompatible."
    assert tcs01.description == "Procedencia: Colombia (AGROSAVIA, Montaña Santandereana)."


def test_the_initial_catalog_can_be_removed_by_reverting(seeded):
    seed.remove_initial_varieties(installed_apps, None)

    assert not CacaoVariety.objects.exists()


def test_reverting_keeps_varieties_added_later(seeded):
    CacaoVariety.objects.create(name="ABC-12", name_normalized="abc12")

    seed.remove_initial_varieties(installed_apps, None)

    assert list(CacaoVariety.objects.values_list("name", flat=True)) == ["ABC-12"]
