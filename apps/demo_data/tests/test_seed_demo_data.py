import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from apps.accounts.models import User
from apps.accounts.system_roles import ADMINISTRATOR, PRODUCER
from apps.accounts.tests.helpers import login_by_email
from apps.crops.models import CacaoVariety, PlotCharacterization
from apps.crops.tests.factories import CacaoVarietyFactory
from apps.demo_data.catalog import (
    DEMO_ADMIN_EMAIL,
    DEMO_PASSWORD,
    DEMO_PRODUCER_EMAIL,
    PRODUCERS,
)
from apps.farms.models import Farm
from apps.plots.models import Plot
from apps.producers.models import Producer

pytestmark = pytest.mark.django_db

VARIETIES_USED = {
    planting["variety"]
    for producer in PRODUCERS
    for farm in producer["farms"]
    for plot in farm["plots"]
    for planting in (plot.get("characterization") or {}).get("plantings", [])
}


def seed():
    call_command("seed_demo_data", stdout=open("/dev/null", "w"))


def counts():
    return (
        Producer.objects.count(),
        Farm.objects.count(),
        Plot.objects.count(),
        PlotCharacterization.objects.count(),
    )


def test_the_demo_administrator_signs_in_with_the_demo_password(api_client):
    seed()

    admin = User.objects.get(email=DEMO_ADMIN_EMAIL)
    assert admin.groups.filter(role__code=ADMINISTRATOR).exists()
    assert admin.producer is None
    assert login_by_email(api_client, DEMO_ADMIN_EMAIL, DEMO_PASSWORD).status_code == 200


def test_the_demo_producer_signs_in_and_owns_records(api_client):
    seed()

    account = User.objects.get(email=DEMO_PRODUCER_EMAIL)
    assert account.groups.filter(role__code=PRODUCER).exists()
    assert account.producer.farms.exists()
    assert Plot.objects.filter(farm__producer=account.producer, boundary__isnull=False).exists()
    assert PlotCharacterization.objects.filter(plot__farm__producer=account.producer).exists()
    assert login_by_email(api_client, DEMO_PRODUCER_EMAIL, DEMO_PASSWORD).status_code == 200


def test_creates_every_producer_with_its_farms_plots_and_characterizations():
    seed()

    farms = [farm for producer in PRODUCERS for farm in producer["farms"]]
    plots = [plot for farm in farms for plot in farm["plots"]]
    characterized = [plot for plot in plots if plot.get("characterization")]
    assert counts() == (len(PRODUCERS), len(farms), len(plots), len(characterized))
    assert Producer.objects.filter(status=Producer.Status.INACTIVE).exists()


def test_the_other_producer_accounts_stay_pending_activation():
    seed()

    others = User.objects.filter(producer__isnull=False).exclude(email=DEMO_PRODUCER_EMAIL)
    assert others.exists()
    assert not any(account.has_usable_password() for account in others)


def test_running_it_again_creates_nothing_new():
    seed()
    before = counts()

    seed()

    assert counts() == before
    assert User.objects.filter(email__in=[DEMO_ADMIN_EMAIL, DEMO_PRODUCER_EMAIL]).count() == 2


def test_running_it_again_restores_the_demo_accounts(api_client):
    seed()
    for account in User.objects.filter(email__in=[DEMO_ADMIN_EMAIL, DEMO_PRODUCER_EMAIL]):
        account.set_password("otra-clave-cualquiera-123")
        account.is_active = False
        account.save()
        account.groups.clear()

    seed()

    for email in (DEMO_ADMIN_EMAIL, DEMO_PRODUCER_EMAIL):
        assert login_by_email(api_client, email, DEMO_PASSWORD).status_code == 200
    assert (
        User.objects.get(email=DEMO_ADMIN_EMAIL).groups.filter(role__code=ADMINISTRATOR).exists()
    )
    assert User.objects.get(email=DEMO_PRODUCER_EMAIL).groups.filter(role__code=PRODUCER).exists()


def test_keeps_a_producer_that_already_exists_untouched():
    seed()
    farm = Farm.objects.filter(producer__accounts__email=DEMO_PRODUCER_EMAIL).first()
    Plot.objects.filter(farm=farm).update(is_active=False)

    seed()

    assert not Plot.objects.filter(farm=farm, is_active=True).exists()


def test_fails_clearly_when_the_variety_catalog_is_missing():
    CacaoVariety.objects.all().delete()

    with pytest.raises(CommandError, match="catálogo de variedades"):
        seed()

    assert counts() == (0, 0, 0, 0)


@pytest.mark.django_db(transaction=True)
def test_sends_no_activation_email():
    # Este tipo de prueba vacía las tablas al terminar, también el catálogo que carga una
    # migración: se vuelve a crear lo que la semilla usa.
    for name in VARIETIES_USED:
        if not CacaoVariety.objects.filter(name=name).exists():
            CacaoVarietyFactory(name=name)

    seed()

    assert mail.outbox == []
