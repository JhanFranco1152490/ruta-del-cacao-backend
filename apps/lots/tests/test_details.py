"""Lo que otras apps agregan a la representación de un lote (su fermentación, su secado)."""

from datetime import date

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import serializers

from apps.common.contracts import lot_details
from apps.lots.tests.test_read import Estate

pytestmark = pytest.mark.django_db


@pytest.fixture
def estate():
    return Estate()


@pytest.fixture
def event_actions(monkeypatch):
    """Un campo de prueba que lee una relación del lote, registrado como lo haría otra app."""
    monkeypatch.setattr(
        lot_details,
        "_fields",
        {
            "event_actions": lambda: serializers.SlugRelatedField(
                source="audit_events", slug_field="action", many=True, read_only=True
            )
        },
    )
    monkeypatch.setattr(lot_details, "_prefetch", ["audit_events"])


def test_a_registered_field_appears_in_the_list_and_the_detail(auth_client, estate, event_actions):
    client = auth_client(estate.owner)

    listed = client.get("/api/lots").data["results"]
    detail = client.get(f"/api/lots/{estate.lot_a.pk}").data

    assert all(item["event_actions"] == [] for item in listed)
    assert detail["event_actions"] == []


def test_the_registered_prefetch_keeps_the_list_from_growing(auth_client, estate, event_actions):
    client = auth_client(estate.owner)
    with CaptureQueriesContext(connection) as few:
        client.get("/api/lots")
    for day in range(1, 11):
        estate.lot(estate.plot_a, date(2026, 9, day), f"000123-F01-P01-2609{day:02d}-1")

    with CaptureQueriesContext(connection) as many:
        response = client.get("/api/lots", {"page_size": 100})

    assert response.data["count"] == 12
    assert len(many) == len(few)


def test_registering_adds_fields_and_does_not_repeat_prefetches(monkeypatch):
    monkeypatch.setattr(lot_details, "_fields", {})
    monkeypatch.setattr(lot_details, "_prefetch", [])

    lot_details.register_lot_details({"a": serializers.CharField}, ["drying"])
    lot_details.register_lot_details({"b": serializers.CharField}, ["drying", "fermentation"])

    assert sorted(lot_details.lot_detail_fields()) == ["a", "b"]
    assert lot_details.lot_detail_prefetch() == ["drying", "fermentation"]
