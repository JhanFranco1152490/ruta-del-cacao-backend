import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.health.choices import PestDiseaseKind
from apps.health.models import PestDisease
from apps.health.tests.factories import PestDiseaseFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "repeated", ["monilia de prueba", "MONILIA DE PRUEBA", " Monília-de prueba "]
)
def test_the_name_is_unique_after_normalization(repeated):
    PestDiseaseFactory(name="Monilia de prueba")

    with pytest.raises(IntegrityError), transaction.atomic():
        PestDiseaseFactory(name=repeated)


def test_clean_trims_the_texts_and_normalizes_the_name():
    pest = PestDisease(
        name="  Chinche – verde ",
        kind=PestDiseaseKind.PEST,
        scientific_name="  Nezara viridula ",
        description=" Pica las mazorcas. ",
    )

    pest.clean()

    assert pest.name == "Chinche – verde"
    assert pest.normalized_name == "chincheverde"
    assert pest.scientific_name == "Nezara viridula"
    assert pest.description == "Pica las mazorcas."
    assert pest.search_normalized == "chincheverde|nezaraviridula"


def test_a_blank_scientific_name_is_stored_as_null():
    pest = PestDisease(name="Chinche", kind=PestDiseaseKind.PEST, scientific_name="  ")

    pest.clean()

    assert pest.scientific_name is None
    assert pest.search_normalized == "chinche"


@pytest.mark.parametrize("name", ["", "   ", " - "])
def test_clean_requires_a_name(name):
    with pytest.raises(ValidationError) as error:
        PestDisease(name=name, kind=PestDiseaseKind.PEST).clean()

    assert "name" in error.value.message_dict


def test_a_new_one_is_active():
    pest = PestDiseaseFactory()

    pest.refresh_from_db()
    assert pest.is_active is True


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


def test_every_initial_one_has_a_field_description_and_can_be_searched():
    for pest in PestDisease.objects.all():
        assert 1 <= len(pest.description) <= 300
        assert pest.search_normalized.startswith(pest.normalized_name)


def test_monilia_is_found_by_its_scientific_name():
    monilia = PestDisease.objects.get(name="Monilia")

    assert "moniliophthoraroreri" in monilia.search_normalized
    assert monilia.description.startswith("Solo ataca la mazorca.")


def test_health_declares_only_the_permissions_something_checks():
    names = dict(
        Permission.objects.filter(content_type__app_label="health").values_list("codename", "name")
    )

    assert names == {
        "manage_pestdisease": (
            "Puede registrar, editar, activar y desactivar plagas y enfermedades"
        ),
    }


def test_choice_values_are_the_ones_the_client_sends():
    assert set(PestDiseaseKind.values) == {"pest", "disease"}
