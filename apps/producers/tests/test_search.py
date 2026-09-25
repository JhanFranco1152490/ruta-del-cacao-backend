import pytest

from .factories import ProducerFactory

pytestmark = pytest.mark.django_db

SEARCH_URL = "/api/producers"


def search(client, term):
    return client.get(SEARCH_URL, {"search": term})


@pytest.mark.parametrize(
    ("stored", "term"),
    [
        ("Pérez", "perez"),
        ("Pérez", "pérez"),
        ("Perez", "pérez"),
        ("Muñoz", "munoz"),
        ("Muñoz", "MUÑOZ"),
        ("Gómez", "gom"),
    ],
)
def test_last_name_search_ignores_accents_and_case(admin_client, stored, term):
    target = ProducerFactory(last_name=stored)
    ProducerFactory(last_name="Rojas")

    response = search(admin_client, term)

    assert [row["id"] for row in response.data["results"]] == [str(target.id)]


def test_first_name_search_ignores_accents(admin_client):
    target = ProducerFactory(first_name="José")
    ProducerFactory(first_name="Ana")

    response = search(admin_client, "jose")

    assert [row["id"] for row in response.data["results"]] == [str(target.id)]


def test_search_combining_words_ignores_accents(admin_client):
    target = ProducerFactory(first_name="Ana", last_name="Pérez")
    ProducerFactory(first_name="Ana", last_name="Gómez")

    response = search(admin_client, "ana perez")

    assert [row["id"] for row in response.data["results"]] == [str(target.id)]


def test_search_by_document_and_member_code_still_works(admin_client):
    target = ProducerFactory()
    ProducerFactory()

    by_document = search(admin_client, target.identity_document)
    by_code = search(admin_client, target.member_code)

    assert [row["id"] for row in by_document.data["results"]] == [str(target.id)]
    assert [row["id"] for row in by_code.data["results"]] == [str(target.id)]
