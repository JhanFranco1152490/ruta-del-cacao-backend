import factory
from factory.django import DjangoModelFactory

from apps.common.text import normalize_catalog_name
from apps.facilities.models import PostharvestFacility
from apps.farms.tests.factories import FarmFactory
from apps.harvests.tests.factories import characterized_plot
from apps.lots.tests.factories import LotFactory


class PostharvestFacilityFactory(DjangoModelFactory):
    class Meta:
        model = PostharvestFacility

    farm = factory.SubFactory(FarmFactory)
    facility_type = PostharvestFacility.FacilityType.FERMENTATION_BOX
    name = factory.Sequence(lambda n: f"C-{n:02d}")
    name_normalized = factory.LazyAttribute(lambda item: normalize_catalog_name(item.name))
    capacity_kg = 600


def facility_data(farm, **overrides) -> dict:
    """Cuerpo válido de un alta, con los nombres de la API."""
    data = {
        "farm_id": farm.pk,
        "facility_type": "fermentation_box",
        "name": "C-04",
        "capacity_kg": 600,
    }
    data.update(overrides)
    return data


def lot_in(farm):
    """Un lote de una cosecha de una parcela de `farm`, para ocupar sus cajones y marquesinas."""
    return LotFactory(harvest__plot=characterized_plot(farm=farm))
