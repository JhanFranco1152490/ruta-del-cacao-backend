import pytest

from apps.common import producer_dependents as dependents
from apps.common.producer_dependents import (
    ProducerDependent,
    register_dependent,
    registered_dependents,
)


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    # El registro real se llena en el arranque de las apps: cada prueba trabaja con uno vacío.
    monkeypatch.setattr(dependents, "_REGISTRY", {})


def _dependent(name, **overrides):
    values = {
        "name": name,
        "important_record": lambda producer: None,
        "count": lambda producer: 0,
        "delete_all": lambda producer, actor: None,
    }
    return ProducerDependent(**{**values, **overrides})


def test_dependents_keep_the_order_they_were_registered_in():
    register_dependent(_dependent("farms"))
    register_dependent(_dependent("accounts"))

    assert [d.name for d in registered_dependents()] == ["farms", "accounts"]


def test_registering_a_name_again_replaces_it_instead_of_duplicating():
    # Volver a cargar un módulo vuelve a registrar: no debe borrar dos veces lo mismo.
    register_dependent(_dependent("farms", count=lambda producer: 1))
    register_dependent(_dependent("farms", count=lambda producer: 2))

    (only,) = registered_dependents()
    assert only.count(None) == 2


def test_the_real_registry_has_farms_and_accounts_after_startup(monkeypatch):
    monkeypatch.undo()

    assert {"farms", "accounts"} <= {d.name for d in registered_dependents()}
