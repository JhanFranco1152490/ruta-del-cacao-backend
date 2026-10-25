from dataclasses import fields as dataclass_fields
from decimal import Decimal

import pytest

from apps.common.contracts import postharvest_parameters as contract
from apps.common.contracts.postharvest_parameters import DryingParameters, drying_parameters
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.fields import FIELDS
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestParametersFactory

pytestmark = pytest.mark.django_db


def test_the_contract_carries_exactly_the_stored_parameters():
    assert [field.name for field in dataclass_fields(DryingParameters)] == list(FIELDS)


def test_the_baseline_is_a_complete_set_of_drying_parameters():
    assert isinstance(DRYING_BASELINE, DryingParameters)


def test_a_producer_without_parameters_reads_the_baseline():
    producer = ProducerFactory()

    assert drying_parameters(producer.pk) == DRYING_BASELINE


def test_a_producer_with_parameters_reads_its_own():
    parameters = PostharvestParametersFactory(
        slow_duration_day=9, overdried_moisture_pct=Decimal("5.5")
    )

    read = drying_parameters(parameters.producer_id)

    assert read.slow_duration_day == 9
    assert read.overdried_moisture_pct == Decimal("5.5")
    assert read.entry_moisture_min_pct == DRYING_BASELINE.entry_moisture_min_pct


def test_the_parameters_of_one_producer_do_not_reach_another():
    PostharvestParametersFactory(slow_duration_day=9)

    assert drying_parameters(ProducerFactory().pk).slow_duration_day == 8


def test_the_contract_fails_clearly_when_nobody_registered_the_reader(monkeypatch):
    monkeypatch.setattr(contract, "_reader", None)

    with pytest.raises(RuntimeError, match="parámetros"):
        drying_parameters(ProducerFactory().pk)
