from dataclasses import asdict

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.common.contracts.producer_dependents import registered_dependents
from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.models import (
    PostharvestParameters,
    PostharvestParametersAuditEvent,
)
from apps.postharvest_parameters.producer_dependent import parameters_dependent
from apps.postharvest_parameters.services.save import save_parameters
from apps.producers.models import Producer
from apps.producers.services import change_producer_status, delete_producer
from apps.producers.tests.factories import ProducerFactory

from .factories import PostharvestParametersFactory

pytestmark = pytest.mark.django_db


def test_the_parameters_are_registered_as_a_dependent_of_the_producer():
    assert parameters_dependent in registered_dependents()


def test_the_parameters_are_never_an_important_record():
    parameters = PostharvestParametersFactory(slow_duration_day=9)

    assert parameters_dependent.important_record(parameters.producer) is None


def test_the_parameters_are_counted():
    parameters = PostharvestParametersFactory()

    assert parameters_dependent.count(parameters.producer) == 1
    assert parameters_dependent.count(ProducerFactory()) == 0


def test_a_producer_created_by_mistake_is_deleted_with_its_parameters_and_their_history():
    producer = ProducerFactory()
    technical = UserFactory(is_superuser=True)
    save_parameters(technical, producer.pk, 0, {**asdict(DRYING_BASELINE), "slow_duration_day": 9})
    other = PostharvestParametersFactory()

    delete_producer(technical, producer.pk, producer.version)

    assert not Producer.objects.filter(pk=producer.pk).exists()
    assert not PostharvestParameters.objects.filter(pk=producer.pk).exists()
    assert not PostharvestParametersAuditEvent.objects.filter(producer_id=producer.pk).exists()
    assert PostharvestParameters.objects.filter(pk=other.pk).exists()


def test_an_inactive_producer_keeps_its_parameters():
    parameters = PostharvestParametersFactory(slow_duration_day=9)
    producer = parameters.producer

    change_producer_status(producer.pk, producer.version, Producer.Status.INACTIVE)

    assert PostharvestParameters.objects.get(pk=producer.pk).slow_duration_day == 9
