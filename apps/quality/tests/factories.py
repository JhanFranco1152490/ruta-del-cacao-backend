from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.lots.choices import LotStatus
from apps.lots.tests.factories import LotFactory
from apps.quality.models import LotClassification, LotDiscard, QualityEvaluation

_same_producer = factory.SelfAttribute("..lot.harvest.plot.farm.producer")


class QualityEvaluationFactory(DjangoModelFactory):
    """La evaluación de un lote Evaluado. No avanza el lote por los servicios: para eso están los
    servicios."""

    class Meta:
        model = QualityEvaluation

    lot = factory.SubFactory(LotFactory, status=LotStatus.EVALUATED)
    well_fermented_pct = Decimal("78.5")
    moldy_pct = Decimal("2.0")
    other_defects_pct = Decimal("4.5")
    evaluated_by = factory.SubFactory(UserFactory, producer=_same_producer)
    evaluated_at = factory.LazyFunction(timezone.now)


class LotClassificationFactory(DjangoModelFactory):
    """La clasificación de un lote Clasificado, sin descarte."""

    class Meta:
        model = LotClassification

    lot = factory.SubFactory(LotFactory, status=LotStatus.CLASSIFIED)
    g1_kg = Decimal("250.0")
    g2_kg = Decimal("63.2")
    discard_kg = Decimal("0.0")
    classified_by = factory.SubFactory(UserFactory, producer=_same_producer)
    classified_at = factory.LazyFunction(timezone.now)


class LotDiscardFactory(DjangoModelFactory):
    """El descarte completo de un lote Descartado, por moho."""

    class Meta:
        model = LotDiscard

    lot = factory.SubFactory(LotFactory, status=LotStatus.DISCARDED)
    reason = "mold"
    discarded_by = factory.SubFactory(UserFactory, producer=_same_producer)
    discarded_at = factory.LazyFunction(timezone.now)
