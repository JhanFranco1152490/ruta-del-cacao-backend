import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.buyers.models import Buyer, BuyerAuditEvent
from apps.producers.tests.factories import ProducerFactory

from .factories import BuyerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


def buyer_url(name, buyer):
    return reverse(f"admin:buyers_buyer_{name}", args=[buyer.pk])


def buyer_form(buyer, **overrides):
    data = {
        "name": buyer.name,
        "document_type": buyer.document_type,
        "identity_document": buyer.identity_document,
        "buyer_type": buyer.buyer_type,
        "contact_name": buyer.contact_name or "",
        "phone": buyer.phone or "",
        "email": buyer.email or "",
        "is_active": "on" if buyer.is_active else "",
        "expected_version": buyer.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    return login(superuser)


def test_the_list_searches_by_name_and_shows_whether_it_has_records(client, buyer_usage_table):
    sold_to = BuyerFactory(name="Cacao Andino")
    buyer_usage_table(sold_to)
    BuyerFactory(name="Bocadillos")

    body = client.get(reverse("admin:buyers_buyer_changelist"), {"q": "andino"}).content.decode()

    assert "Cacao Andino" in body
    assert "Bocadillos" not in body
    assert 'alt="True"' in body


def test_saving_a_buyer_goes_through_the_service_and_the_history_names_the_admin(
    client, superuser
):
    buyer = BuyerFactory(name="Cacao Andino")

    response = client.post(buyer_url("change", buyer), buyer_form(buyer, name="Cacao Andino SAS"))

    assert response.status_code == 302
    buyer.refresh_from_db()
    assert (buyer.name, buyer.version) == ("Cacao Andino SAS", 2)
    event = BuyerAuditEvent.objects.get(buyer_ref=buyer.pk, action="updated")
    assert event.actor == superuser


def test_deactivating_a_buyer_is_a_status_change_in_the_history(client):
    buyer = BuyerFactory()

    client.post(buyer_url("change", buyer), buyer_form(buyer, is_active=""))

    buyer.refresh_from_db()
    assert not buyer.is_active
    assert BuyerAuditEvent.objects.filter(buyer_ref=buyer.pk, action="status_changed").exists()


def test_the_producer_of_a_buyer_cannot_be_changed_from_the_form(client):
    buyer = BuyerFactory()
    producer_id = buyer.producer_id

    client.post(
        buyer_url("change", buyer),
        buyer_form(buyer, name="Otro nombre", producer=ProducerFactory().pk),
    )

    buyer.refresh_from_db()
    assert (buyer.name, buyer.producer_id) == ("Otro nombre", producer_id)


def test_a_stale_form_is_rejected_and_changes_nothing(client):
    buyer = BuyerFactory(name="Cacao Andino")
    stale = buyer_form(buyer, name="Tardío")
    Buyer.objects.filter(pk=buyer.pk).update(version=2)

    response = client.post(buyer_url("change", buyer), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    buyer.refresh_from_db()
    assert (buyer.name, buyer.version) == ("Cacao Andino", 2)


def test_a_repeated_document_is_refused_with_the_services_message(client):
    buyer = BuyerFactory()
    other = BuyerFactory(producer=buyer.producer)

    response = client.post(
        buyer_url("change", buyer),
        buyer_form(buyer, identity_document=other.identity_document),
        follow=True,
    )

    assert "Ya tienes registrado un comprador con este documento" in response.content.decode()
    buyer.refresh_from_db()
    assert buyer.version == 1


def test_nobody_can_add_buyers_from_the_admin(client):
    assert client.get(reverse("admin:buyers_buyer_add")).status_code == 403


def test_a_buyer_without_records_is_deleted_through_the_service_and_leaves_its_trace(
    client, superuser
):
    buyer = BuyerFactory()

    response = client.post(buyer_url("delete", buyer), {"post": "yes"})

    assert response.status_code == 302
    assert not Buyer.objects.filter(pk=buyer.pk).exists()
    event = BuyerAuditEvent.objects.get(buyer_ref=buyer.pk, action="deleted")
    assert event.actor == superuser


def test_a_buyer_with_records_is_not_deleted_and_the_admin_says_why(client, buyer_usage_table):
    buyer = BuyerFactory()
    buyer_usage_table(buyer)

    response = client.post(buyer_url("delete", buyer), {"post": "yes"}, follow=True)

    assert Buyer.objects.filter(pk=buyer.pk).exists()
    assert "tiene ventas registradas" in response.content.decode()


def test_the_bulk_delete_action_is_not_offered(client):
    BuyerFactory()

    body = client.get(reverse("admin:buyers_buyer_changelist")).content.decode()

    assert "delete_selected" not in body


def test_staff_who_is_not_the_technical_account_only_reaches_its_own_producers_buyers():
    mine = BuyerFactory(name="Comprador mío")
    theirs = BuyerFactory(name="Comprador ajeno")
    client = login(
        UserFactory(
            is_staff=True,
            producer=mine.producer,
            permissions=["buyers.view_buyer", "buyers.change_buyer"],
        )
    )

    body = client.get(reverse("admin:buyers_buyer_changelist")).content.decode()

    assert "Comprador mío" in body and "Comprador ajeno" not in body
    assert client.get(buyer_url("change", theirs)).status_code == 302


def test_the_history_is_read_only_and_only_for_the_superuser(client):
    buyer = BuyerFactory()
    client.post(buyer_url("change", buyer), buyer_form(buyer, name="Otro nombre"))
    event = BuyerAuditEvent.objects.get()
    base = "admin:buyers_buyerauditevent"

    assert client.get(reverse(f"{base}_changelist")).status_code == 200
    assert client.get(reverse(f"{base}_change", args=[event.pk])).status_code == 200
    assert client.get(reverse(f"{base}_add")).status_code == 403
    assert (
        client.post(reverse(f"{base}_delete", args=[event.pk]), {"post": "yes"}).status_code == 403
    )
    employee = login(UserFactory(is_staff=True, permissions=["buyers.view_buyer"]))
    assert employee.get(reverse(f"{base}_changelist")).status_code == 403
