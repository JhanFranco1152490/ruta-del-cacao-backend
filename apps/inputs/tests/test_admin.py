import pytest
from django.test import Client
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory
from apps.inputs.models import AgriculturalInput, AgriculturalInputAuditEvent, InputStock
from apps.inputs.services import create_input, update_input
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory, InputMovementFactory, input_data

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("plain_static_files")]


def login(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def event():
    owner = UserFactory(producer=ProducerFactory())
    item = create_input(owner, input_data(name="Urea"))
    update_input(owner, item.pk, 1, {"name": "Urea 46 %"})
    return AgriculturalInputAuditEvent.objects.get(action="updated")


def changelist_url():
    return reverse("admin:inputs_agriculturalinputauditevent_changelist")


def change_url(event):
    return reverse("admin:inputs_agriculturalinputauditevent_change", args=[event.pk])


def test_a_superuser_reads_the_history_with_its_values(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    assert client.get(changelist_url()).status_code == 200
    detail = client.get(change_url(event))
    assert detail.status_code == 200
    assert "Urea 46 %" in detail.content.decode()


def test_staff_with_the_inputs_permission_does_not_read_the_history(event):
    # El admin no filtra por productor: con el permiso de la API vería los insumos de todos.
    client = login(UserFactory(is_staff=True, permissions=["inputs.view_agriculturalinput"]))

    assert client.get(changelist_url()).status_code == 403
    assert client.get(change_url(event)).status_code == 403


def test_the_history_cannot_be_changed_from_the_admin(event):
    client = login(UserFactory(is_staff=True, is_superuser=True))

    add = client.get(reverse("admin:inputs_agriculturalinputauditevent_add"))
    delete = client.post(
        reverse("admin:inputs_agriculturalinputauditevent_delete", args=[event.pk]),
        {"post": "yes"},
    )

    assert add.status_code == 403
    assert delete.status_code == 403
    assert AgriculturalInputAuditEvent.objects.filter(pk=event.pk).exists()


# --- Insumos, existencias y movimientos ---


def input_url(name, item):
    return reverse(f"admin:inputs_agriculturalinput_{name}", args=[item.pk])


def input_form(item, **overrides):
    data = {
        "name": item.name,
        "input_type": item.input_type,
        "unit": item.unit,
        "package_type": item.package_type or "",
        "package_size": item.package_size or "",
        "is_active": "on" if item.is_active else "",
        "expected_version": item.version,
    }
    data.update(overrides)
    return {name: value for name, value in data.items() if value != ""}


@pytest.fixture
def superuser():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.fixture
def client(superuser):
    return login(superuser)


def test_the_input_list_searches_by_name_and_by_producer(client):
    item = AgriculturalInputFactory(name="Urea 46 %")
    AgriculturalInputFactory(name="Cal agrícola")

    by_name = client.get(reverse("admin:inputs_agriculturalinput_changelist"), {"q": "urea"})
    by_producer = client.get(
        reverse("admin:inputs_agriculturalinput_changelist"),
        {"q": item.producer.member_code},
    )

    assert "Urea 46 %" in by_name.content.decode()
    assert "Cal agrícola" not in by_name.content.decode()
    assert "Cal agrícola" not in by_producer.content.decode()


def test_saving_an_input_goes_through_the_service_and_the_history_names_the_admin(
    client, superuser
):
    item = AgriculturalInputFactory(name="Urea")

    response = client.post(input_url("change", item), input_form(item, name="Urea 46 %"))

    assert response.status_code == 302
    item.refresh_from_db()
    assert (item.name, item.version) == ("Urea 46 %", 2)
    event = AgriculturalInputAuditEvent.objects.get(input_ref=item.pk, action="updated")
    assert event.actor == superuser


def test_deactivating_an_input_is_a_status_change_in_the_history(client):
    item = AgriculturalInputFactory()

    client.post(input_url("change", item), input_form(item, is_active=""))

    item.refresh_from_db()
    assert not item.is_active
    assert AgriculturalInputAuditEvent.objects.filter(
        input_ref=item.pk, action="status_changed"
    ).exists()


def test_the_producer_of_an_input_cannot_be_changed_from_the_form(client):
    item = AgriculturalInputFactory()
    producer_id = item.producer_id

    client.post(
        input_url("change", item),
        input_form(item, name="Otro", producer=ProducerFactory().pk),
    )

    item.refresh_from_db()
    assert (item.name, item.producer_id) == ("Otro", producer_id)


def test_a_stale_form_for_an_input_is_rejected_and_changes_nothing(client):
    item = AgriculturalInputFactory(name="Urea")
    stale = input_form(item, name="Tardío")
    AgriculturalInput.objects.filter(pk=item.pk).update(version=2)

    response = client.post(input_url("change", item), stale)

    assert "Otra persona modificó este registro" in response.content.decode()
    item.refresh_from_db()
    assert (item.name, item.version) == ("Urea", 2)


def test_a_repeated_name_and_type_is_refused_with_the_services_message(client):
    item = AgriculturalInputFactory(name="Urea")
    AgriculturalInputFactory(producer=item.producer, name="Cal")

    response = client.post(input_url("change", item), input_form(item, name="Cal"), follow=True)

    assert "Ya existe un insumo con este nombre y tipo" in response.content.decode()
    item.refresh_from_db()
    assert item.version == 1


def test_the_unit_of_an_input_with_movements_cannot_change(client):
    movement = InputMovementFactory()
    item = movement.input

    response = client.post(input_url("change", item), input_form(item, unit="g"), follow=True)

    assert "ya tiene movimientos" in response.content.decode()
    item.refresh_from_db()
    assert (item.unit, item.version) == ("kg", 1)


def test_nobody_can_add_inputs_from_the_admin(client):
    assert client.get(reverse("admin:inputs_agriculturalinput_add")).status_code == 403


def test_an_input_created_by_mistake_is_deleted_through_the_service_and_leaves_its_trace(
    client, superuser
):
    item = AgriculturalInputFactory()

    response = client.post(input_url("delete", item), {"post": "yes"})

    assert response.status_code == 302
    assert not AgriculturalInput.objects.filter(pk=item.pk).exists()
    event = AgriculturalInputAuditEvent.objects.get(input_ref=item.pk, action="deleted")
    assert event.actor == superuser


def test_an_input_with_records_is_not_deleted_and_the_admin_says_why(client):
    item = InputMovementFactory().input

    response = client.post(input_url("delete", item), {"post": "yes"}, follow=True)

    assert AgriculturalInput.objects.filter(pk=item.pk).exists()
    assert "tiene registros asociados" in response.content.decode()


def test_the_bulk_delete_action_is_not_offered_for_inputs(client):
    AgriculturalInputFactory()

    body = client.get(reverse("admin:inputs_agriculturalinput_changelist")).content.decode()

    assert "delete_selected" not in body


def test_staff_who_is_not_the_technical_account_only_reaches_its_own_producers_inputs():
    mine = AgriculturalInputFactory(name="Insumo mío")
    theirs = AgriculturalInputFactory(name="Insumo ajeno")
    client = login(
        UserFactory(
            is_staff=True,
            producer=mine.producer,
            permissions=["inputs.view_agriculturalinput", "inputs.change_agriculturalinput"],
        )
    )

    body = client.get(reverse("admin:inputs_agriculturalinput_changelist")).content.decode()

    assert "Insumo mío" in body and "Insumo ajeno" not in body
    assert client.get(input_url("change", theirs)).status_code == 302


@pytest.mark.parametrize("model", ["inputstock", "inputmovement"])
def test_stock_and_movements_are_read_only_and_only_for_the_superuser(client, model):
    movement = InputMovementFactory()
    stock = InputStock.objects.create(input=movement.input, farm=movement.farm, quantity=100)
    record = stock if model == "inputstock" else movement
    base = f"admin:inputs_{model}"

    assert client.get(reverse(f"{base}_changelist")).status_code == 200
    assert client.get(reverse(f"{base}_change", args=[record.pk])).status_code == 200
    assert client.get(reverse(f"{base}_add")).status_code == 403
    assert client.post(reverse(f"{base}_change", args=[record.pk]), {}).status_code == 403
    assert (
        client.post(reverse(f"{base}_delete", args=[record.pk]), {"post": "yes"}).status_code
        == 403
    )
    employee = login(UserFactory(is_staff=True, permissions=["inputs.view_agriculturalinput"]))
    assert employee.get(reverse(f"{base}_changelist")).status_code == 403
