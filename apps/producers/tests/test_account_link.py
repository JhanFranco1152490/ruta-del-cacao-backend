import pytest
from django.core import mail

from apps.accounts.models import User
from apps.accounts.system_roles import PRODUCER, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.roles import enable_association_access, grant_role, make_producer_owner
from apps.producers.models import Producer
from apps.producers.tests.factories import ProducerFactory

pytestmark = pytest.mark.django_db


def producer_url(producer) -> str:
    return f"/api/producers/{producer.id}"


# --- account -------------------------------------------------------------------------------------


def test_detail_without_account_has_a_null_account(client_with):
    producer = ProducerFactory()

    response = client_with("producers.view").get(producer_url(producer))

    assert response.status_code == 200
    assert response.data["account"] is None
    assert response.data["association_access"] is False


def test_detail_with_account_reflects_it(client_with):
    producer = ProducerFactory()
    owner = make_producer_owner(producer)

    response = client_with("producers.view").get(producer_url(producer))

    account = response.data["account"]
    assert str(account["id"]) == str(owner.id)
    assert account["email"] == owner.email
    assert account["status"] == "active"
    # make_producer_owner es un atajo de prueba (UserFactory con contraseña utilizable), no
    # el alta real: no representa una cuenta pendiente de activación.
    assert account["activation_pending"] is False


def test_detail_does_not_confuse_an_employee_with_the_producer_account(client_with):
    producer = ProducerFactory()
    UserFactory(producer=producer)  # empleado, sin el rol Productor

    response = client_with("producers.view").get(producer_url(producer))

    assert response.data["account"] is None


def test_detail_reflects_the_association_access_switch(client_with):
    producer = ProducerFactory()
    make_producer_owner(producer)

    off = client_with("producers.view").get(producer_url(producer))
    assert off.data["association_access"] is False

    enable_association_access(producer)

    on = client_with("producers.view").get(producer_url(producer))
    assert on.data["association_access"] is True


def test_list_does_not_include_the_new_fields(client_with):
    make_producer_owner(ProducerFactory())

    response = client_with("producers.view").get("/api/producers")

    result = response.data["results"][0]
    assert "account" not in result
    assert "association_access" not in result


def test_detail_queries_do_not_grow_with_the_number_of_accounts(
    client_with, django_assert_max_num_queries
):
    producer = ProducerFactory()
    make_producer_owner(producer)
    enable_association_access(producer)
    for _ in range(15):
        UserFactory(producer=ProducerFactory())

    client = client_with("producers.view")
    with django_assert_max_num_queries(10):
        response = client.get(producer_url(producer))

    assert response.status_code == 200


# --- sincronización al editar el expediente ------------------------------------------------------


def test_updating_the_producer_syncs_the_linked_accounts_document_and_names(client_with):
    producer = ProducerFactory(first_name="Ana", last_name="Original")
    owner = make_producer_owner(producer)

    response = client_with("producers.update").patch(
        producer_url(producer),
        {"first_name": "Beatriz", "last_name": "Nueva", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    owner.refresh_from_db()
    assert (owner.first_name, owner.last_name) == ("Beatriz", "Nueva")


def test_updating_the_producers_document_syncs_the_account(client_with):
    producer = ProducerFactory(identity_document="10000001")
    owner = make_producer_owner(producer)

    response = client_with("producers.update").patch(
        producer_url(producer),
        {"identity_document": "10000002", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    owner.refresh_from_db()
    assert owner.identity_document == "10000002"


def test_a_document_colliding_with_an_unrelated_account_reverts_everything(client_with):
    producer = ProducerFactory(document_type="CC", identity_document="10000001")
    # A diferencia de make_producer_owner, aquí el documento de la cuenta se deja igual al
    # del expediente a propósito: así representa lo que create_account (HU-03) ya garantiza.
    owner = grant_role(
        UserFactory(producer=producer, document_type="CC", identity_document="10000001"),
        get_system_role(PRODUCER),
    )
    grant_role(
        UserFactory(document_type="CC", identity_document="99999999"), get_system_role(PRODUCER)
    )

    response = client_with("producers.update").patch(
        producer_url(producer),
        {"identity_document": "99999999", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert "existing_producer_id" not in response.data
    producer.refresh_from_db()
    owner.refresh_from_db()
    assert producer.identity_document == "10000001"
    assert producer.version == 1
    assert owner.identity_document == "10000001"


def test_updating_fields_not_mirrored_does_not_touch_the_account(client_with):
    # El teléfono es propio de la cuenta (HU-03), no del expediente: cambiarlo en el
    # productor no debe sobrescribirlo.
    producer = ProducerFactory(phone=None)
    owner = make_producer_owner(producer)
    owner.phone = "3009999999"
    owner.save(update_fields=["phone"])

    response = client_with("producers.update").patch(
        producer_url(producer),
        {"phone": "3001234567", "expected_version": 1},
        format="json",
    )

    assert response.status_code == 200
    same_owner = User.objects.get(pk=owner.pk)
    assert same_owner.phone == "3009999999"


# --- alta automática de la cuenta Productor --------------------------------------------------


def test_creating_a_producer_creates_its_account(client_with):
    response = client_with("producers.create").post(
        "/api/producers",
        {
            "document_type": "CC",
            "identity_document": "30000001",
            "first_name": "Carlos",
            "last_name": "Nuevo",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
            "email": "carlos@example.com",
        },
        format="json",
    )

    assert response.status_code == 201
    producer_id = response.data["id"]
    account = User.objects.get(producer_id=producer_id)
    assert account.email == "carlos@example.com"
    assert account.document_type == "CC"
    assert account.identity_document == "30000001"
    assert (account.first_name, account.last_name) == ("Carlos", "Nuevo")
    assert not account.has_usable_password()
    assert account.groups.filter(role__code=PRODUCER).exists()
    assert response.data["account"]["id"] == str(account.id)


def test_creating_a_producer_sends_the_activation_email(
    client_with, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = client_with("producers.create").post(
            "/api/producers",
            {
                "document_type": "CC",
                "identity_document": "30000002",
                "first_name": "Diana",
                "last_name": "Nueva",
                "municipality_code": "54001",
                "joined_on": "2026-09-21",
                "email": "diana@example.com",
            },
            format="json",
        )

    assert response.status_code == 201
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["diana@example.com"]


def test_creating_a_producer_with_a_duplicate_account_email_creates_nothing(client_with):
    grant_role(
        UserFactory(email="tomado@example.com"),
        get_system_role(PRODUCER),
    )
    count_before = Producer.objects.count()

    response = client_with("producers.create").post(
        "/api/producers",
        {
            "document_type": "CC",
            "identity_document": "30000003",
            "first_name": "Eva",
            "last_name": "Nueva",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
            "email": "tomado@example.com",
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_email"
    assert Producer.objects.count() == count_before


def test_creating_a_producer_with_a_duplicate_account_document_creates_nothing(client_with):
    grant_role(
        UserFactory(document_type="CC", identity_document="30000004"),
        get_system_role(PRODUCER),
    )
    count_before = Producer.objects.count()

    response = client_with("producers.create").post(
        "/api/producers",
        {
            "document_type": "CC",
            "identity_document": "30000004",
            "first_name": "Fabián",
            "last_name": "Nuevo",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
            "email": "fabian@example.com",
        },
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "duplicate_document"
    assert "existing_producer_id" not in response.data
    assert Producer.objects.count() == count_before


def test_editing_a_producer_does_not_create_a_second_account(client_with):
    client = client_with("producers.create", "producers.update")
    created = client.post(
        "/api/producers",
        {
            "document_type": "CC",
            "identity_document": "30000005",
            "first_name": "Gloria",
            "last_name": "Original",
            "municipality_code": "54001",
            "joined_on": "2026-09-21",
            "email": "gloria@example.com",
        },
        format="json",
    )
    producer_id = created.data["id"]

    client.patch(
        f"/api/producers/{producer_id}",
        {"first_name": "Gloria Editada", "expected_version": 1},
        format="json",
    )

    assert User.objects.filter(producer_id=producer_id).count() == 1
