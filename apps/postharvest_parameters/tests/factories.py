from dataclasses import asdict

import factory
from factory.django import DjangoModelFactory

from apps.postharvest_parameters.baseline import DRYING_BASELINE
from apps.postharvest_parameters.models import PostharvestParameters
from apps.producers.tests.factories import ProducerFactory


class PostharvestParametersFactory(DjangoModelFactory):
    """Parámetros guardados con los valores de la línea base; cada prueba cambia los que le
    importan."""

    class Meta:
        model = PostharvestParameters

    producer = factory.SubFactory(ProducerFactory)

    @classmethod
    def _adjust_kwargs(cls, **kwargs):
        return {**asdict(DRYING_BASELINE), **kwargs}
