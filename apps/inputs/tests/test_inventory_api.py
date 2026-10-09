import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.system_roles import FOREMAN, get_system_role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    grant_role,
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.farms.models import Farm
from apps.farms.tests.factories import FarmFactory
from apps.inputs.models import AgriculturalInput, InputMovement
from apps.inputs.services import record_consumption, register_movement
from apps.producers.tests.factories import ProducerFactory

from .factories import AgriculturalInputFactory

pytestmark = pytest.mark.django_db

STOCKS = "/api/input-stocks"
MOVEMENTS = "/api/input-movements"
TODAY = timezone.localdate()


@pytest.fixture
def producer():
    return ProducerFactory()


@pytest.fixture
def owner(producer):
    return make_producer_owner(producer)


@pytest.fixture
def foreman(producer):
    return grant_role(UserFactory(producer=producer), get_system_role(FOREMAN))


@pytest.fixture
def farm(producer):
    return FarmFactory(producer=producer)


@pytest.fixture
def item(producer):
    return AgriculturalInputFactory(producer=producer, unit="ml", name="Cobre")


def body(item, farm, **overrides):
    data = {
        "input_id": str(item.pk),
        "farm_id": str(farm.pk),
        "kind": "entry",
        "quantity": "300",
        "occurred_on": TODAY.isoformat(),
    }
    data.update(overrides)
    return {key: value for key, value in data.items() if value is not None}


def entry(user, item, farm, amount="300", **extra):
    return register_movement(
        user,
        {
            "input_id": item.pk,
            "farm_id": farm.pk,
            "kind": "entry",
            "quantity": Decimal(amount),
            "occurred_on": TODAY,
            **extra,
        },
    )


# --- Permisos ---


def test_the_routes_need_a_session(anonymous_client, item, farm):
    assert anonymous_client.get(STOCKS, {"farm": str(farm.pk)}).status_code == 401
    assert anonymous_client.get(MOVEMENTS).status_code == 401
    assert anonymous_client.post(MOVEMENTS, body(item, farm), format="json").status_code == 401


def test_the_association_has_no_access_to_the_inventory(auth_client, item, farm):
    client = auth_client(make_administrator())

    assert client.get(STOCKS, {"farm": str(farm.pk)}).status_code == 403
    assert client.post(MOVEMENTS, body(item, farm), format="json").status_code == 403


def test_viewing_does_not_allow_registering(auth_client, producer, item, farm):
    viewer = make_delegate(producer, ["inputs.view_agriculturalinput"])
    client = auth_client(viewer)

    assert client.get(STOCKS, {"farm": str(farm.pk)}).status_code == 200
    assert client.post(MOVEMENTS, body(item, farm), format="json").status_code == 403


def test_the_foreman_registers_movements(auth_client, foreman, item, farm):
    assert auth_client(foreman).post(MOVEMENTS, body(item, farm), format="json").status_code == 201


def test_a_delegate_with_the_stock_permission_registers_movements(
    auth_client, producer, item, farm
):
    delegate = make_delegate(producer, ["inputs.manage_inputstock"])

    assert (
        auth_client(delegate).post(MOVEMENTS, body(item, farm), format="json").status_code == 201
    )


# --- Registrar ---


def test_an_entry_answers_201_with_the_movement_and_the_stock(auth_client, owner, item, farm):
    response = auth_client(owner).post(
        MOVEMENTS, body(item, farm, note="Compra de octubre"), format="json"
    )

    assert response.status_code == 201
    assert response.data["movement"]["kind"] == "entry"
    assert response.data["movement"]["quantity"] == "300.000"
    assert response.data["movement"]["counted_quantity"] is None
    assert response.data["movement"]["note"] == "Compra de octubre"
    assert response.data["stock"]["quantity"] == "300.000"
    assert response.data["stock"]["input_id"] == str(item.pk)
    assert response.data["stock"]["last_count_date"] is None


def test_a_count_answers_with_the_difference_and_the_last_count_date(
    auth_client, owner, item, farm
):
    entry(owner, item, farm, "250")

    response = auth_client(owner).post(
        MOVEMENTS,
        body(item, farm, kind="count", quantity=None, counted_quantity="230"),
        format="json",
    )

    assert response.status_code == 201
    assert response.data["movement"]["quantity"] == "-20.000"
    assert response.data["movement"]["counted_quantity"] == "230.000"
    assert response.data["stock"]["quantity"] == "230.000"
    assert response.data["stock"]["last_count_date"] == TODAY.isoformat()


def test_resending_the_same_id_answers_200_without_duplicating(auth_client, owner, item, farm):
    client = auth_client(owner)
    data = body(item, farm, id=str(uuid.uuid4()))
    first = client.post(MOVEMENTS, data, format="json")

    again = client.post(MOVEMENTS, data, format="json")

    assert (first.status_code, again.status_code) == (201, 200)
    assert again.data["movement"]["id"] == first.data["movement"]["id"]
    assert again.data["stock"]["quantity"] == "300.000"
    assert InputMovement.objects.count() == 1


def test_resending_an_id_with_other_content_answers_409(auth_client, owner, item, farm):
    client = auth_client(owner)
    movement_id = str(uuid.uuid4())
    client.post(MOVEMENTS, body(item, farm, id=movement_id), format="json")

    response = client.post(
        MOVEMENTS, body(item, farm, id=movement_id, quantity="1"), format="json"
    )

    assert response.status_code == 409
    assert response.data["code"] == "movement_id_conflict"


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"quantity": "0"}, "quantity"),
        ({"quantity": "-3"}, "quantity"),
        ({"quantity": None}, "quantity"),
        ({"quantity": "1.2345"}, "quantity"),
        ({"quantity": "10000000"}, "quantity"),
        ({"quantity": "abc"}, "quantity"),
        ({"counted_quantity": "5"}, "counted_quantity"),
        ({"kind": "consumption"}, "kind"),
        ({"kind": None}, "kind"),
        ({"occurred_on": (TODAY + timedelta(days=1)).isoformat()}, "occurred_on"),
        ({"occurred_on": None}, "occurred_on"),
        ({"note": "x" * 201}, "note"),
        ({"input_id": None}, "input_id"),
        ({"farm_id": None}, "farm_id"),
        ({"surprise": 1}, None),
    ],
)
def test_an_invalid_entry_answers_400_and_writes_nothing(
    auth_client, owner, item, farm, changes, field
):
    response = auth_client(owner).post(MOVEMENTS, body(item, farm, **changes), format="json")

    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    if field:
        assert field in response.data["fields"]
    assert not InputMovement.objects.exists()


@pytest.mark.parametrize(
    "changes, field",
    [
        ({"counted_quantity": "-1"}, "counted_quantity"),
        ({"counted_quantity": None}, "counted_quantity"),
        ({"quantity": "5"}, "quantity"),
    ],
)
def test_an_invalid_count_answers_400(auth_client, owner, item, farm, changes, field):
    overrides = {"kind": "count", "quantity": None, "counted_quantity": "10", **changes}
    data = body(item, farm, **overrides)

    response = auth_client(owner).post(MOVEMENTS, data, format="json")

    assert response.status_code == 400
    assert field in response.data["fields"]


def test_an_inactive_input_rejects_entries_but_accepts_counts(auth_client, owner, item, farm):
    AgriculturalInput.objects.filter(pk=item.pk).update(is_active=False)
    client = auth_client(owner)

    entry_response = client.post(MOVEMENTS, body(item, farm), format="json")
    count_response = client.post(
        MOVEMENTS,
        body(item, farm, kind="count", quantity=None, counted_quantity="0"),
        format="json",
    )

    assert entry_response.status_code == 422
    assert entry_response.data["code"] == "input_inactive"
    assert count_response.status_code == 201


def test_an_inactive_farm_rejects_movements(auth_client, owner, item, farm):
    Farm.objects.filter(pk=farm.pk).update(is_active=False)

    response = auth_client(owner).post(MOVEMENTS, body(item, farm), format="json")

    assert response.status_code == 422
    assert response.data["code"] == "farm_inactive"


def test_someone_elses_input_or_farm_answers_404(auth_client, owner, item, farm):
    client = auth_client(owner)

    foreign_input = client.post(MOVEMENTS, body(AgriculturalInputFactory(), farm), format="json")
    foreign_farm = client.post(MOVEMENTS, body(item, FarmFactory()), format="json")

    assert (foreign_input.status_code, foreign_farm.status_code) == (404, 404)
    assert not InputMovement.objects.exists()


def test_the_technical_account_registers_but_not_across_producers(auth_client, item, farm):
    client = auth_client(UserFactory(is_superuser=True))

    assert client.post(MOVEMENTS, body(item, farm), format="json").status_code == 201
    mixed = client.post(MOVEMENTS, body(item, FarmFactory()), format="json")
    assert mixed.status_code == 400
    assert "farm_id" in mixed.data["fields"]


def test_another_farm_of_the_producer_keeps_its_own_stock(
    auth_client, owner, producer, item, farm
):
    other = FarmFactory(producer=producer)
    client = auth_client(owner)
    client.post(MOVEMENTS, body(item, farm), format="json")

    assert client.get(STOCKS, {"farm": str(other.pk)}).data["results"] == []


# --- Existencias ---


def test_stocks_list_only_inputs_with_movements_in_the_farm(
    auth_client, owner, producer, item, farm
):
    AgriculturalInputFactory(producer=producer, name="Sin movimientos")
    entry(owner, item, farm, "250")
    record_consumption(item, farm, Decimal("300"), TODAY, "Fertilización · P-03", owner)

    response = auth_client(owner).get(STOCKS, {"farm": str(farm.pk)})

    assert response.status_code == 200
    assert response.data["results"] == [
        {
            "input_id": str(item.pk),
            "farm_id": str(farm.pk),
            "quantity": "-50.000",
            "last_count_date": None,
            "updated_at": response.data["results"][0]["updated_at"],
        }
    ]


def test_stocks_need_the_farm(auth_client, owner):
    response = auth_client(owner).get(STOCKS)

    assert response.status_code == 400
    assert "farm" in response.data["fields"]


def test_the_stocks_of_a_foreign_farm_are_empty(auth_client, owner):
    foreign_item = AgriculturalInputFactory()
    foreign_farm = FarmFactory(producer=foreign_item.producer)
    entry(UserFactory(producer=foreign_item.producer), foreign_item, foreign_farm)

    response = auth_client(owner).get(STOCKS, {"farm": str(foreign_farm.pk)})

    assert (response.status_code, response.data["results"]) == (200, [])


def test_the_technical_account_reads_the_stocks_of_any_farm(auth_client, owner, item, farm):
    entry(owner, item, farm)

    response = auth_client(UserFactory(is_superuser=True)).get(STOCKS, {"farm": str(farm.pk)})

    assert len(response.data["results"]) == 1


# --- Movimientos ---


def test_movements_come_newest_first_with_signed_quantities(auth_client, owner, item, farm):
    entry(owner, item, farm, "300", occurred_on=TODAY - timedelta(days=2), note="Compra")
    record_consumption(item, farm, Decimal("50"), TODAY, "Fertilización · P-03", owner)

    response = auth_client(owner).get(MOVEMENTS, {"input": str(item.pk), "farm": str(farm.pk)})

    assert response.status_code == 200
    assert response.data["count"] == 2
    kinds = [(row["kind"], row["quantity"]) for row in response.data["results"]]
    assert kinds == [("consumption", "-50.000"), ("entry", "300.000")]
    assert response.data["results"][0]["note"] == "Fertilización · P-03"
    assert set(response.data["results"][0]) == {
        "id",
        "kind",
        "quantity",
        "counted_quantity",
        "occurred_on",
        "note",
        "actor_name",
        "created_at",
    }


def test_movements_are_paginated(auth_client, owner, item, farm):
    for _ in range(3):
        entry(owner, item, farm, "1")

    response = auth_client(owner).get(
        MOVEMENTS, {"input": str(item.pk), "farm": str(farm.pk), "page_size": 2}
    )

    assert (response.data["count"], len(response.data["results"])) == (3, 2)
    assert response.data["next"] is not None


def test_the_actor_name_is_null_when_the_account_was_deleted(
    auth_client, owner, producer, item, farm
):
    gone = UserFactory(producer=producer)
    entry(gone, item, farm)
    gone.delete()

    response = auth_client(owner).get(MOVEMENTS, {"input": str(item.pk), "farm": str(farm.pk)})

    assert response.data["results"][0]["actor_name"] is None


def test_movements_need_the_input_and_the_farm(auth_client, owner, item, farm):
    client = auth_client(owner)

    assert client.get(MOVEMENTS, {"input": str(item.pk)}).status_code == 400
    assert client.get(MOVEMENTS, {"farm": str(farm.pk)}).status_code == 400


def test_the_movements_of_a_foreign_input_or_farm_answer_404(auth_client, owner, item, farm):
    client = auth_client(owner)

    foreign_input = client.get(
        MOVEMENTS, {"input": str(AgriculturalInputFactory().pk), "farm": str(farm.pk)}
    )
    foreign_farm = client.get(MOVEMENTS, {"input": str(item.pk), "farm": str(FarmFactory().pk)})
    missing = client.get(MOVEMENTS, {"input": str(uuid.uuid4()), "farm": str(farm.pk)})

    assert (foreign_input.status_code, foreign_farm.status_code, missing.status_code) == (
        404,
        404,
        404,
    )


def test_a_count_dated_before_a_movement_answers_400(auth_client, owner, item, farm):
    entry(owner, item, farm, "100", occurred_on=TODAY)

    response = auth_client(owner).post(
        MOVEMENTS,
        body(
            item,
            farm,
            kind="count",
            quantity=None,
            counted_quantity="40",
            occurred_on=(TODAY - timedelta(days=2)).isoformat(),
        ),
        format="json",
    )

    assert response.status_code == 400
    assert "occurred_on" in response.data["fields"]
