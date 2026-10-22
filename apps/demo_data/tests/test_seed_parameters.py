from dataclasses import asdict

import pytest

from apps.accounts.models import User
from apps.common.contracts.postharvest_parameters import drying_parameters
from apps.demo_data.catalog import DEMO_DRYING_PARAMETERS, DEMO_PRODUCER_EMAIL
from apps.demo_data.parameters import seed_drying_parameters
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.models import PostharvestParametersAuditEvent
from apps.postharvest_parameters.services.save import save_parameters
from apps.producers.models import Producer

from .test_seed_demo_data import seed

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    seed()
    return User.objects.get(email=DEMO_PRODUCER_EMAIL)


def test_the_demo_producer_has_customized_drying_parameters(owner):
    parameters = drying_parameters(owner.producer_id)

    for name, value in DEMO_DRYING_PARAMETERS.items():
        assert getattr(parameters, name) == value
    assert parameters.overdried_moisture_pct == DRYING_BASELINE.overdried_moisture_pct
    event = PostharvestParametersAuditEvent.objects.get(producer_id=owner.producer_id)
    assert event.actor == owner


def test_the_other_producers_use_the_baseline(owner):
    others = Producer.objects.exclude(pk=owner.producer_id)

    assert others.exists()
    assert all(drying_parameters(producer.pk) == DRYING_BASELINE for producer in others)


def test_seeding_again_adds_nothing(owner):
    assert seed_drying_parameters(owner) == []
    assert (
        PostharvestParametersAuditEvent.objects.filter(producer_id=owner.producer_id).count() == 1
    )


def test_parameters_changed_from_the_app_are_kept(owner):
    values = {**asdict(drying_parameters(owner.producer_id)), "accelerated_day": 2}
    save_parameters(owner, None, 1, values)

    seed()

    assert drying_parameters(owner.producer_id).accelerated_day == 2
