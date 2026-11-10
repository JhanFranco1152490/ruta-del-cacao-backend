import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import UserFactory
from apps.buyers.tests.factories import BuyerFactory
from apps.farms.tests.factories import FarmFactory
from apps.sales.models import Sale, SaleLine
from apps.warehouse.tests.factories import StockExitFactory


class SaleFactory(DjangoModelFactory):
    """Una venta sin líneas, sin pasar por los servicios: no descuenta existencias."""

    class Meta:
        model = Sale

    farm = factory.SubFactory(FarmFactory)
    producer = factory.SelfAttribute("farm.producer")
    buyer = factory.SubFactory(BuyerFactory, producer=factory.SelfAttribute("..producer"))
    number = factory.Sequence(lambda n: n + 1)
    sale_date = factory.LazyFunction(timezone.localdate)
    created_by = factory.SubFactory(UserFactory, producer=factory.SelfAttribute("..producer"))
    created_at = factory.LazyFunction(timezone.now)


class SaleLineFactory(DjangoModelFactory):
    """Una línea con su salida de bodega por venta, sin pasar por los servicios."""

    class Meta:
        model = SaleLine

    sale = factory.SubFactory(SaleFactory)
    stock_exit = factory.SubFactory(StockExitFactory, reason="sale")
    lot = factory.SelfAttribute("stock_exit.lot")
    grade = factory.SelfAttribute("stock_exit.grade")
    quantity_kg = factory.SelfAttribute("stock_exit.quantity_kg")
    price_per_kg = 18500
    subtotal = factory.LazyAttribute(lambda line: round(line.quantity_kg * line.price_per_kg))
