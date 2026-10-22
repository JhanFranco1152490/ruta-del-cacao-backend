from dataclasses import asdict
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.fields import FIELDS, RANGE_PAIRS
from apps.postharvest_parameters.models import PostharvestParameters

from .factories import PostharvestParametersFactory

pytestmark = pytest.mark.django_db


def test_the_baseline_has_every_parameter_and_nothing_else():
    assert set(asdict(DRYING_BASELINE)) == set(FIELDS)
    assert len(FIELDS) == 15


def test_the_model_stores_every_parameter():
    stored = {field.name for field in PostharvestParameters._meta.concrete_fields}

    assert set(FIELDS) <= stored


@pytest.mark.parametrize(("low", "high"), RANGE_PAIRS)
def test_every_baseline_range_starts_below_its_end(low, high):
    assert getattr(DRYING_BASELINE, low) <= getattr(DRYING_BASELINE, high)


def test_the_baseline_passes_every_database_check():
    parameters = PostharvestParametersFactory()

    parameters.refresh_from_db()
    assert parameters.version == 1
    assert parameters.slow_duration_day == 8
    assert parameters.overdried_moisture_pct == Decimal("6.0")


@pytest.mark.parametrize(
    "values",
    [
        {"entry_moisture_max_pct": Decimal("100.1")},
        {"overdried_moisture_pct": Decimal("-0.1")},
        {"estimated_days_min": 0},
        {"estimated_days_max": 61},
        {"slow_duration_day": 0},
        {"accelerated_day": 61},
        {"slow_stall_window_hours": 0},
        {"slow_stall_window_hours": 241},
        {"slow_stall_min_drop_pct": Decimal("0.0")},
        {"entry_moisture_min_pct": Decimal("61.0")},
        {"target_moisture_min_pct": Decimal("7.6")},
        {"estimated_days_min": 8},
        {"near_target_min_pct": Decimal("8.6")},
    ],
)
def test_the_database_rejects_a_value_out_of_its_range(values):
    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestParametersFactory(**values)


@pytest.mark.parametrize(
    "values",
    [
        {"entry_moisture_min_pct": Decimal("0.0"), "entry_moisture_max_pct": Decimal("100.0")},
        {"estimated_days_min": 1, "estimated_days_max": 60},
        {"slow_stall_window_hours": 240},
        {"near_target_min_pct": Decimal("8.0"), "near_target_max_pct": Decimal("8.0")},
    ],
)
def test_the_database_accepts_the_edges_of_each_range(values):
    PostharvestParametersFactory(**values)


def test_a_producer_has_at_most_one_set_of_parameters():
    parameters = PostharvestParametersFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        PostharvestParametersFactory(producer=parameters.producer)
