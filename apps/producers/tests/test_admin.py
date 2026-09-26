import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.producers.models import Producer

from .factories import ProducerFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]

STALE_NOTICE = "Otra persona modificó esta ficha"


def staff_client(*permissions, superuser=False):
    client = Client()
    client.force_login(
        UserFactory(is_staff=True, is_superuser=superuser, permissions=list(permissions))
    )
    return client


def changelist_url():
    return reverse("admin:producers_producer_changelist")


def change_url(producer):
    return reverse("admin:producers_producer_change", args=[producer.pk])


def form_data(producer, **overrides):
    data = {
        "first_name": producer.first_name,
        "last_name": producer.last_name,
        "phone": producer.phone or "",
        "email": producer.email or "",
        "municipality_code": producer.municipality_code,
        "joined_on": producer.joined_on.isoformat(),
        "expected_version": producer.version,
    }
    return {**data, **overrides}


def run_action(client, action, *producers):
    return client.post(
        changelist_url(),
        {"action": action, "_selected_action": [str(producer.pk) for producer in producers]},
        follow=True,
    )


def test_list_needs_the_view_permission():
    assert staff_client().get(changelist_url()).status_code == 403
    assert staff_client("producers.view").get(changelist_url()).status_code == 200


def test_list_shows_document_and_municipality_name_and_searches_without_accents():
    target = ProducerFactory(last_name="Pérez", identity_document="1098765432")
    ProducerFactory(last_name="Gómez")

    body = staff_client("producers.view").get(changelist_url(), {"q": "perez"}).content.decode()

    assert change_url(target) in body
    assert "Gómez" not in body
    assert "CC 1098765432" in body
    assert "Cúcuta" in body


def test_nobody_can_add_or_delete_producers_from_the_admin(api_client):
    producer = ProducerFactory()
    client = staff_client(superuser=True)

    assert client.get(reverse("admin:producers_producer_add")).status_code == 403
    deletion = client.post(
        reverse("admin:producers_producer_delete", args=[producer.pk]), {"post": "yes"}
    )
    assert deletion.status_code == 403
    assert Producer.objects.filter(pk=producer.pk).exists()


def test_viewing_without_the_update_permission_is_read_only():
    producer = ProducerFactory()
    client = staff_client("producers.view")

    assert client.get(change_url(producer)).status_code == 200
    response = client.post(change_url(producer), form_data(producer, first_name="Otro"))

    assert response.status_code == 403
    producer.refresh_from_db()
    assert producer.first_name == "Ana"


def test_change_page_carries_the_version_the_form_was_opened_at():
    producer = ProducerFactory()

    body = staff_client("producers.view", "producers.update").get(change_url(producer))

    assert f'name="expected_version" value="{producer.version}"' in body.content.decode()


def test_saving_goes_through_the_service_and_bumps_the_version(admin_client):
    producer = ProducerFactory(first_name="Ana", phone="3001234567")
    client = staff_client("producers.view", "producers.update")

    response = client.post(
        change_url(producer),
        form_data(producer, first_name="Carla", phone="3007654321"),
    )

    assert response.status_code == 302
    producer.refresh_from_db()
    assert (producer.first_name, producer.phone, producer.version) == ("Carla", "3007654321", 2)
    # Quien tenía la ficha abierta en la aplicación recibe el conflicto en vez de pisar el cambio.
    stale = admin_client.patch(
        f"/api/producers/{producer.pk}",
        {"first_name": "Otra", "expected_version": 1},
        format="json",
    )
    assert stale.status_code == 409
    assert stale.data["code"] == "stale_version"


def test_saving_without_changes_does_not_bump_the_version():
    producer = ProducerFactory()
    client = staff_client("producers.view", "producers.update")

    assert client.post(change_url(producer), form_data(producer)).status_code == 302

    producer.refresh_from_db()
    assert producer.version == 1


def test_identity_status_and_code_cannot_be_changed_from_the_form():
    producer = ProducerFactory(identity_document="1098765432", member_code="PROD-900001")
    client = staff_client("producers.view", "producers.update", "producers.change_status")

    client.post(
        change_url(producer),
        form_data(
            producer,
            identity_document="5555555555",
            document_type="CE",
            member_code="PROD-000001",
            status="inactive",
            version=99,
        ),
    )

    producer.refresh_from_db()
    assert producer.identity_document == "1098765432"
    assert producer.document_type == "CC"
    assert producer.member_code == "PROD-900001"
    assert producer.status == Producer.Status.ACTIVE
    assert producer.version == 1


def test_a_stale_form_is_rejected_and_changes_nothing():
    producer = ProducerFactory(first_name="Ana")
    client = staff_client("producers.view", "producers.update")
    opened = form_data(producer, first_name="Carla")
    Producer.objects.filter(pk=producer.pk).update(first_name="Berta", version=2)

    response = client.post(change_url(producer), opened)

    assert response.status_code == 200
    assert STALE_NOTICE in response.content.decode()
    producer.refresh_from_db()
    assert (producer.first_name, producer.version) == ("Berta", 2)


def test_blank_phone_and_email_are_stored_as_null():
    producer = ProducerFactory(phone="3001234567", email="ana@example.com")
    client = staff_client("producers.view", "producers.update")

    client.post(change_url(producer), form_data(producer, phone="", email=""))

    producer.refresh_from_db()
    assert producer.phone is None
    assert producer.email is None


def test_the_municipality_must_come_from_the_catalog():
    producer = ProducerFactory()
    client = staff_client("producers.view", "producers.update")

    response = client.post(change_url(producer), form_data(producer, municipality_code="99999"))

    assert response.status_code == 200
    producer.refresh_from_db()
    assert producer.municipality_code == "54001"
    assert producer.version == 1


def test_status_actions_change_the_status_and_bump_the_version():
    active = ProducerFactory()
    inactive = ProducerFactory(status=Producer.Status.INACTIVE)
    client = staff_client("producers.view", "producers.change_status")

    run_action(client, "deactivate", active, inactive)
    for producer in (active, inactive):
        producer.refresh_from_db()
    assert (active.status, active.version) == (Producer.Status.INACTIVE, 2)
    assert (inactive.status, inactive.version) == (Producer.Status.INACTIVE, 1)

    run_action(client, "activate", active)
    active.refresh_from_db()
    assert (active.status, active.version) == (Producer.Status.ACTIVE, 3)


def test_status_actions_need_the_change_status_permission():
    producer = ProducerFactory()
    client = staff_client("producers.view", "producers.update")

    run_action(client, "deactivate", producer)

    producer.refresh_from_db()
    assert (producer.status, producer.version) == (Producer.Status.ACTIVE, 1)
    assert "deactivate" not in client.get(changelist_url()).content.decode()


def test_the_delete_action_is_not_offered():
    ProducerFactory()

    body = staff_client(superuser=True).get(changelist_url()).content.decode()

    assert "delete_selected" not in body
