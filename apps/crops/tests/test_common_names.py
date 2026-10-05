from importlib import import_module

import pytest
from django.apps import apps as installed_apps

from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import make_administrator
from apps.crops.models import CacaoVariety, CacaoVarietyAuditEvent
from apps.crops.tests.factories import CacaoVarietyFactory, PlotPlantingFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("empty_catalog")]

URL = "/api/cacao-varieties"

# Las pruebas con `transaction=True` vacían las tablas, también lo que llenaron las migraciones:
# se llaman sus funciones en vez de confiar en lo que dejaron.
initial = import_module("apps.crops.migrations.0002_seed_cacao_varieties")
common = import_module("apps.crops.migrations.0004_seed_common_names")


@pytest.fixture
def admin_client(auth_client):
    return auth_client(make_administrator())


def register(client, **fields):
    return client.post(URL, {"name": "FSA-12", **fields}, format="json")


# --- Registrar y editar -------------------------------------------------------------------------


def test_a_variety_is_registered_with_its_common_names(admin_client):
    response = register(admin_client, common_names=["Saravena", "Fedecacao Saravena"])

    assert response.status_code == 201
    assert response.data["common_names"] == ["Saravena", "Fedecacao Saravena"]


def test_common_names_are_optional(admin_client):
    response = register(admin_client)

    assert response.status_code == 201
    assert response.data["common_names"] == []


def test_the_same_common_name_can_belong_to_several_varieties(admin_client):
    register(admin_client, common_names=["Saravena"])

    response = register(admin_client, name="FSA-13", common_names=["Saravena"])

    assert response.status_code == 201


def test_common_names_are_trimmed_and_not_repeated_within_a_variety(admin_client):
    response = register(admin_client, common_names=[" Saravena ", "saravena", "SARAVENA"])

    assert response.data["common_names"] == ["Saravena"]


@pytest.mark.parametrize(
    "common_names",
    [["a", "b", "c", "d", "e", "f"], ["x" * 61], [""], "Saravena"],
    ids=["six", "too_long", "blank", "not_a_list"],
)
def test_invalid_common_names_are_rejected(admin_client, common_names):
    response = register(admin_client, common_names=common_names)

    assert response.status_code == 400
    assert "common_names" in response.data["fields"]


def test_five_common_names_of_sixty_characters_are_accepted(admin_client):
    names = [f"{index}{'x' * 59}" for index in range(5)]

    response = register(admin_client, common_names=names)

    assert response.status_code == 201


def test_editing_the_common_names_leaves_an_event_that_names_the_field(admin_client):
    variety = CacaoVarietyFactory(name="FSA-12")

    response = admin_client.patch(
        f"{URL}/{variety.pk}", {"common_names": ["Saravena"]}, format="json"
    )

    assert response.status_code == 200
    event = CacaoVarietyAuditEvent.objects.get(variety_ref=variety.pk)
    assert event.changed_fields == ["common_names"]


# --- Búsqueda -----------------------------------------------------------------------------------


@pytest.mark.parametrize("term", ["saravena", "SARAVENA", "Fedecacao Saravena"])
def test_the_search_finds_varieties_by_their_common_name(admin_client, term):
    for name in ("FSA-11", "FSA-12", "FSA-13"):
        register(admin_client, name=name, common_names=["Saravena", "Fedecacao Saravena"])
    register(admin_client, name="FLE-2", common_names=["Lebrija"])

    response = admin_client.get(URL, {"search": term})

    assert [item["name"] for item in response.data["results"]] == ["FSA-11", "FSA-12", "FSA-13"]


def test_the_search_does_not_join_the_end_of_one_name_with_the_next(admin_client):
    # "51" del final de CCN-51 seguido de "co" del nombre común: no es un término real.
    register(admin_client, name="CCN-51", common_names=["Colección Castro Naranjal"])

    response = admin_client.get(URL, {"search": "51co"})

    assert response.data["results"] == []


def test_renaming_keeps_the_search_up_to_date(admin_client):
    variety = CacaoVarietyFactory(name="FSA-12")
    admin_client.patch(f"{URL}/{variety.pk}", {"common_names": ["Saravena"]}, format="json")

    response = admin_client.get(URL, {"search": "saravena"})

    assert [item["name"] for item in response.data["results"]] == ["FSA-12"]


def test_any_account_reads_the_common_names(auth_client):
    CacaoVarietyFactory(name="FSA-12", common_names=["Saravena"])

    response = auth_client(UserFactory()).get(URL)

    assert response.data["results"][0]["common_names"] == ["Saravena"]


# --- Migración de datos -------------------------------------------------------------------------


@pytest.fixture
def seeded():
    initial.add_initial_varieties(installed_apps, None)
    common.add_common_names(installed_apps, None)


def names_of(name):
    return CacaoVariety.objects.get(name=name).common_names


def test_the_migration_adds_fsv_41_with_its_common_names(seeded):
    assert names_of("FSV-41") == ["San Vicente", "Fedecacao San Vicente"]
    assert CacaoVariety.objects.get(name="FSV-41").is_active


def test_the_migration_fills_the_colombian_clones(seeded):
    assert names_of("FSA-11") == names_of("FSA-12") == ["Saravena", "Fedecacao Saravena"]
    assert names_of("SCC-61")[0] == names_of("FSV-41")[0] == "San Vicente"
    assert names_of("TCS-13")[0] == "La Suiza"


def test_international_clones_keep_only_their_code(seeded):
    assert names_of("ICS-95") == []
    assert names_of("TSH-565") == []


def test_the_seeded_common_names_are_searchable(seeded, auth_client):
    response = auth_client(UserFactory()).get(URL, {"search": "san vicente"})

    assert [item["name"] for item in response.data["results"]] == ["FSV-41", "SCC-61"]


def test_the_migration_keeps_what_the_association_already_wrote():
    initial.add_initial_varieties(installed_apps, None)
    CacaoVariety.objects.filter(name="FSA-12").update(common_names=["El de Saravena"])

    common.add_common_names(installed_apps, None)

    assert names_of("FSA-12") == ["El de Saravena"]


def test_the_migration_does_not_repeat_fsv_41_if_it_was_registered():
    initial.add_initial_varieties(installed_apps, None)
    CacaoVarietyFactory(name="FSV 41")

    common.add_common_names(installed_apps, None)

    assert CacaoVariety.objects.filter(name_normalized="fsv41").count() == 1


def test_reverting_removes_fsv_41_only_if_no_planting_uses_it(seeded):
    PlotPlantingFactory(variety=CacaoVariety.objects.get(name="FSV-41"))

    common.remove_common_names(installed_apps, None)

    assert CacaoVariety.objects.filter(name="FSV-41").exists()
