import pytest

from apps.common.contracts import reports
from apps.common.contracts.reports import (
    REPORT_SOURCES,
    register_report_source,
    report_source,
)
from apps.common.contracts.sources import SourceRegistry


def test_a_registered_source_is_returned_by_its_name():
    registry = SourceRegistry("de prueba", {"plots"})

    def plots():
        return []

    registry.register("plots", plots)

    assert registry.get("plots") is plots


def test_asking_for_a_source_nobody_registered_fails_loudly():
    with pytest.raises(RuntimeError):
        SourceRegistry("de prueba", {"plots"}).get("plots")


def test_a_source_outside_the_known_names_cannot_be_registered():
    with pytest.raises(ValueError):
        SourceRegistry("de prueba", {"plots"}).register("activities", lambda: [])


def test_every_report_source_was_registered_by_its_app():
    for name in REPORT_SOURCES:
        assert callable(report_source(name))


def test_the_report_registry_only_takes_its_own_names(monkeypatch):
    monkeypatch.setattr(reports, "_registry", SourceRegistry("de reportes", REPORT_SOURCES))

    with pytest.raises(ValueError):
        register_report_source("farm_scope", lambda: None)
