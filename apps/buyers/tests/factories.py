import factory
from factory.django import DjangoModelFactory

from apps.buyers.models import Buyer
from apps.producers.tests.factories import ProducerFactory


class BuyerFactory(DjangoModelFactory):
    class Meta:
        model = Buyer

    producer = factory.SubFactory(ProducerFactory)
    name = factory.Sequence(lambda n: f"Comprador {n:03d}")
    document_type = "NIT"
    identity_document = factory.Sequence(lambda n: f"{900000000 + n}")
    buyer_type = Buyer.BuyerType.CHOCOLATE_INDUSTRY
    phone = "3001234567"


def buyer_data(**overrides) -> dict:
    """Cuerpo válido de un alta, con los nombres de la API."""
    data = {
        "name": "Chocolates del Oriente S.A.S.",
        "document_type": "NIT",
        "identity_document": "900123456",
        "buyer_type": "chocolate_industry",
        "phone": "3001234567",
    }
    data.update(overrides)
    return data
