import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_catalog_name
from apps.health.choices import PestDiseaseKind
from apps.health.models import PestDisease, search_text


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
