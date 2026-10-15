from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

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


def done_monitoring(**kwargs):
    return done_activity(activity_type=ActivityType.PHYTOSANITARY_MONITORING, **kwargs)


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
