import pytest

from apps.reports.request_serializers import (
    AssociationReportQuerySerializer,
    ProducerReportQuerySerializer,
)

PERIOD = {"from": "2026-01-01", "to": "2026-03-31"}


def errors(serializer_class, data):
    serializer = serializer_class(data=data)
    assert not serializer.is_valid()
    return serializer.errors


def test_the_type_is_required():
    assert set(errors(ProducerReportQuerySerializer, PERIOD)) == {"type"}


@pytest.mark.parametrize(
    "report_type", ["production", "quality", "inventory", "sales", "traceability"]
)
def test_the_producer_has_five_types(report_type):
    data = {**PERIOD, "type": report_type}
    assert ProducerReportQuerySerializer(data=data).is_valid()


@pytest.mark.parametrize("report_type", ["inventory", "traceability", "audit"])
def test_the_association_only_has_production_quality_and_sales(report_type):
    data = {**PERIOD, "type": report_type}
    assert set(errors(AssociationReportQuerySerializer, data)) == {"type"}


def test_the_period_is_required_except_for_the_inventory():
    assert set(errors(ProducerReportQuerySerializer, {"type": "production"})) == {"from", "to"}

    serializer = ProducerReportQuerySerializer(data={"type": "inventory"})
    assert serializer.is_valid()
    assert serializer.validated_data == {"type": "inventory"}


def test_the_inventory_ignores_a_period_it_is_sent():
    serializer = ProducerReportQuerySerializer(
        data={"type": "inventory", "from": "2026-03-01", "to": "2026-01-01"}
    )

    assert serializer.is_valid()
    assert "from" not in serializer.validated_data


def test_the_end_cannot_be_before_the_start():
    data = {"type": "production", "from": "2026-03-01", "to": "2026-02-28"}
    assert set(errors(ProducerReportQuerySerializer, data)) == {"to"}


def test_the_period_is_at_most_366_days():
    ok = {"type": "sales", "from": "2025-01-01", "to": "2026-01-01"}
    too_long = {"type": "sales", "from": "2025-01-01", "to": "2026-01-02"}

    assert ProducerReportQuerySerializer(data=ok).is_valid()
    assert set(errors(ProducerReportQuerySerializer, too_long)) == {"to"}


def test_the_producer_filters_are_ids():
    data = {**PERIOD, "type": "production", "farm": "x", "plot": "y", "lot": "z"}
    assert set(errors(ProducerReportQuerySerializer, data)) == {"farm", "plot", "lot"}


def test_the_association_filters_by_municipality_producer_and_farm():
    serializer = AssociationReportQuerySerializer(
        data={
            **PERIOD,
            "type": "quality",
            "municipality": "54001",
            "producer": "4c1e3f8a-1111-4222-8333-444455556666",
            "farm": "b71e3f8a-1111-4222-8333-444455556666",
        }
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["municipality"] == "54001"


def test_a_municipality_outside_the_catalog_is_rejected():
    data = {**PERIOD, "type": "quality", "municipality": "11001"}
    assert set(errors(AssociationReportQuerySerializer, data)) == {"municipality"}
