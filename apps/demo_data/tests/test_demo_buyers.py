"""Los compradores y el Comercializador de la semilla. Llama a la semilla sin el comando: las
pruebas que lo usan abren `/dev/null`, que no existe en Windows."""

import pytest

from apps.accounts.models import User
from apps.accounts.system_roles import SALES_MANAGER, get_system_role
from apps.accounts.tests.helpers import login_by_email
from apps.buyers.models import Buyer
from apps.demo_data.catalog import (
    DEMO_BUYERS,
    DEMO_PASSWORD,
    DEMO_PRODUCER_EMAIL,
    DEMO_SALES_MANAGER_EMAIL,
)
from apps.demo_data.seed import seed_demo_data

pytestmark = pytest.mark.django_db

URL = "/api/buyers"


@pytest.fixture
def seeded():
    seed_demo_data()
    return User.objects.get(email=DEMO_PRODUCER_EMAIL).producer


def test_the_seed_leaves_one_buyer_of_each_type_and_one_inactive(seeded):
    buyers = Buyer.objects.filter(producer=seeded)

    assert buyers.count() == len(DEMO_BUYERS)
    assert set(buyers.values_list("buyer_type", flat=True)) == set(Buyer.BuyerType.values)
    assert list(buyers.filter(is_active=False).values_list("name", flat=True)) == [
        "Comercializadora El Trapiche"
    ]
    assert buyers.filter(phone__isnull=True).exists()
    assert buyers.filter(email__isnull=True).exists()
    assert buyers.filter(contact_name__isnull=True).exists()


def test_running_it_again_creates_no_buyer_and_keeps_changes(seeded):
    edited = Buyer.objects.get(producer=seeded, identity_document="900000002")
    Buyer.objects.filter(pk=edited.pk).update(name="Nombre cambiado en la aplicación")

    seed_demo_data()

    assert Buyer.objects.filter(producer=seeded).count() == len(DEMO_BUYERS)
    edited.refresh_from_db()
    assert edited.name == "Nombre cambiado en la aplicación"


def test_the_sales_manager_signs_in_with_the_demo_password_and_sees_every_farm(seeded, api_client):
    manager = User.objects.get(email=DEMO_SALES_MANAGER_EMAIL)

    assert manager.producer == seeded
    assert manager.all_farms
    assert get_system_role(SALES_MANAGER).group in manager.groups.all()
    assert login_by_email(api_client, DEMO_SALES_MANAGER_EMAIL, DEMO_PASSWORD).status_code == 200


def test_running_it_again_restores_the_sales_manager(seeded, api_client):
    manager = User.objects.get(email=DEMO_SALES_MANAGER_EMAIL)
    manager.is_active = False
    manager.set_password("OtraClave2026")
    manager.save()

    seed_demo_data()

    assert login_by_email(api_client, DEMO_SALES_MANAGER_EMAIL, DEMO_PASSWORD).status_code == 200


def test_the_demo_flow_of_the_sales_manager(seeded, auth_client):
    client = auth_client(User.objects.get(email=DEMO_SALES_MANAGER_EMAIL))

    listed = client.get(URL).data["results"]
    assert len(listed) == len(DEMO_BUYERS)

    created = client.post(
        URL,
        {
            "name": "Chocolatería La Montaña",
            "document_type": "NIT",
            "identity_document": "901234567",
            "buyer_type": "artisan_processor",
            "email": "pedidos.montana@example.com",
        },
        format="json",
    )
    assert created.status_code == 201

    # El caso negativo: el NIT de Chocolates del Oriente ya está registrado.
    repeated = client.post(
        URL,
        {
            "name": "Otro nombre",
            "document_type": "NIT",
            "identity_document": "900000001",
            "buyer_type": "chocolate_industry",
            "phone": "3009999999",
        },
        format="json",
    )
    assert repeated.status_code == 409
    assert repeated.data["existing"]["name"] == "Chocolates del Oriente S.A.S."

    buyer = created.data
    edited = client.patch(
        f"{URL}/{buyer['id']}",
        {"phone": "3005550000", "expected_version": buyer["version"]},
        format="json",
    )
    off = client.patch(
        f"{URL}/{buyer['id']}",
        {"is_active": False, "expected_version": edited.data["version"]},
        format="json",
    )
    assert (edited.status_code, off.status_code, off.data["is_active"]) == (200, 200, False)
