import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.common.choices import DocumentType
from apps.producers.models import Producer


class ProducerFactory(DjangoModelFactory):
    class Meta:
        model = Producer

    # Rango alto para no chocar con los códigos que asigna la secuencia real en el mismo test.
    member_code = factory.Sequence(lambda n: f"PROD-{900_000 + n:06d}")
    document_type = DocumentType.CC
    identity_document = factory.Sequence(lambda n: str(20_000_000 + n))
    first_name = "Ana"
    last_name = factory.Sequence(lambda n: f"Apellido{n:03d}")
    municipality_code = "54001"
    joined_on = factory.LazyFunction(timezone.localdate)
