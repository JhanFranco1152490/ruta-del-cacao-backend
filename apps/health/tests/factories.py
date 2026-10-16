from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.activities.choices import ActivityType
from apps.activities.tests.factories import AgriculturalActivityFactory, done_activity
from apps.common.text import normalize_catalog_name
from apps.health.choices import PestDiseaseKind, SamplingUnit
from apps.health.models import (
    Detection,
    PestDisease,
    PhytosanitaryMonitoring,
    PhytosanitaryTreatment,
    search_text,
)


class PestDiseaseFactory(DjangoModelFactory):
    class Meta:
        model = PestDisease

    # Nombres que no existen en el catálogo inicial, para no chocar con él.
    name = factory.Sequence(lambda n: f"Plaga de prueba {n:03d}")
    normalized_name = factory.LazyAttribute(lambda pest: normalize_catalog_name(pest.name))
    kind = PestDiseaseKind.PEST
    scientific_name = None
    description = "Se ve en las hojas."
    search_normalized = factory.LazyAttribute(
        lambda pest: search_text(pest.name, pest.scientific_name)
    )


def done_monitoring(done_date=None, **kwargs):
    activity = done_activity(activity_type=ActivityType.PHYTOSANITARY_MONITORING, **kwargs)
    if done_date is not None:
        activity.done_date = done_date
        activity.save(update_fields=["done_date"])
    return activity


class PhytosanitaryMonitoringFactory(DjangoModelFactory):
    class Meta:
        model = PhytosanitaryMonitoring

    activity = factory.LazyFunction(done_monitoring)
    sampling_unit = SamplingUnit.TREES
    evaluated_units = 50


class DetectionFactory(DjangoModelFactory):
    class Meta:
        model = Detection

    monitoring = factory.SubFactory(PhytosanitaryMonitoringFactory)
    pest_disease = factory.SubFactory(PestDiseaseFactory)
    affected_units = 12
    incidence = Decimal("24.00")

    class Params:
        # Quien registró el monitoreo pidió que le programen un control.
        requested = factory.Trait(
            control_requested_by=factory.SubFactory(
                UserFactory,
                producer=factory.SelfAttribute("..monitoring.activity.plot.farm.producer"),
            ),
            control_requested_at=factory.LazyFunction(timezone.now),
        )


class PhytosanitaryTreatmentFactory(DjangoModelFactory):
    """El vínculo de un control programado con la detección que atiende."""

    class Meta:
        model = PhytosanitaryTreatment

    detection = factory.SubFactory(DetectionFactory)
    activity = factory.LazyAttribute(
        lambda treatment: AgriculturalActivityFactory(
            plot=treatment.detection.monitoring.activity.plot,
            activity_type=ActivityType.PHYTOSANITARY_CONTROL,
        )
    )
