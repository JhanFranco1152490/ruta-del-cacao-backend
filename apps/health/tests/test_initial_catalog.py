from importlib import import_module

import pytest
from django.apps import apps as installed_apps

from apps.health.choices import PestDiseaseKind
from apps.health.models import PestDisease

pytestmark = pytest.mark.django_db

# Las pruebas con `transaction=True` vacían las tablas al terminar, también las que llenó una
# migración, así que se llama a la función de la migración en vez de confiar en lo que dejó.
seed = import_module("apps.health.migrations.0002_initial_catalog")
suggestions = import_module("apps.health.migrations.0007_initial_suggestions")


@pytest.fixture(autouse=True)
def initial_catalog():
    PestDisease.objects.all().delete()
    seed.add_initial_catalog(installed_apps, None)
    suggestions.add_suggestions(installed_apps, None)


INITIAL_CATALOG = {
    "Monilia": (PestDiseaseKind.DISEASE, "Moniliophthora roreri"),
    "Mazorca negra": (PestDiseaseKind.DISEASE, "Phytophthora spp."),
    "Escoba de bruja": (PestDiseaseKind.DISEASE, "Moniliophthora perniciosa"),
    "Mal del machete": (
        PestDiseaseKind.DISEASE,
        "Ceratocystis cacaofunesta (antes C. fimbriata)",
    ),
    "Rosellinia o pudrición de la raíz": (PestDiseaseKind.DISEASE, "Rosellinia spp."),
    "Monalonion o chinche del cacao": (PestDiseaseKind.PEST, "Monalonion dissimulatum"),
    "Perforador o pasador de la mazorca": (PestDiseaseKind.PEST, "Carmenta spp."),
    "Gusanos defoliadores": (PestDiseaseKind.PEST, "Dione juno, Eulepidotis spp., entre otros"),
    "Trips": (PestDiseaseKind.PEST, "Selenothrips rubrocinctus"),
    "Cochinilla o piojo blanco": (PestDiseaseKind.PEST, "Planococcus citri"),
    "Barrenadores del tallo": (PestDiseaseKind.PEST, "Xyleborus spp."),
    "Hormiga arriera": (PestDiseaseKind.PEST, "Atta spp."),
}


def test_the_initial_catalog_is_loaded():
    loaded = {
        pest.name: (pest.kind, pest.scientific_name)
        for pest in PestDisease.objects.filter(is_active=True)
    }

    assert loaded == INITIAL_CATALOG


def test_every_initial_one_suggests_what_to_measure():
    assert not PestDisease.objects.filter(suggested_sampling_unit__isnull=True).exists()


@pytest.mark.parametrize(
    "name, unit, method",
    [
        ("Monilia", "pods", "fruit_removal"),
        ("Mazorca negra", "pods", "fruit_removal"),
        ("Escoba de bruja", "trees", "sanitary_pruning"),
        ("Hormiga arriera", "trees", None),
    ],
)
def test_the_suggestions_of_the_common_ones(name, unit, method):
    pest = PestDisease.objects.get(name=name)

    assert (pest.suggested_sampling_unit, pest.suggested_control_method) == (unit, method)


def test_the_suggestions_do_not_overwrite_what_the_association_chose():
    PestDisease.objects.filter(name="Monilia").update(
        suggested_sampling_unit="trees", suggested_control_method="other"
    )

    suggestions.add_suggestions(installed_apps, None)

    monilia = PestDisease.objects.get(name="Monilia")
    assert (monilia.suggested_sampling_unit, monilia.suggested_control_method) == (
        "trees",
        "other",
    )


def test_every_initial_one_has_a_field_description_and_can_be_searched():
    for pest in PestDisease.objects.all():
        assert 1 <= len(pest.description) <= 300
        assert pest.search_normalized.startswith(pest.normalized_name)


def test_monilia_is_found_by_its_scientific_name():
    monilia = PestDisease.objects.get(name="Monilia")

    assert "moniliophthoraroreri" in monilia.search_normalized
    assert monilia.description.startswith("Solo ataca la mazorca.")


def test_removing_the_initial_catalog_leaves_what_the_association_added():
    PestDisease.objects.create(
        name="Chinche verde",
        normalized_name="chincheverde",
        kind=PestDiseaseKind.PEST,
        description="Pica las mazorcas.",
    )

    seed.remove_initial_catalog(installed_apps, None)

    assert list(PestDisease.objects.values_list("name", flat=True)) == ["Chinche verde"]
