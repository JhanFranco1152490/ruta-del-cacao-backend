"""La trazabilidad pública por la API: sin sesión, sin datos personales y con límite por IP."""

import json

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.lots.public_views import PublicTraceabilityThrottle
from apps.lots.tests.factories import LotQrCodeFactory
from apps.lots.tests.journey import Journey

pytestmark = pytest.mark.django_db

TOKEN = "Xq3k9Lm2Pz7tRw1a"
URL = f"/api/public/lots/{TOKEN}"


@pytest.fixture
def journey():
    return Journey()


@pytest.fixture
def sold(journey):
    """Un lote en bodega con ventas (una anulada), una salida, personas con nombre y su QR."""
    lot = journey.sold_lot()
    LotQrCodeFactory(lot=lot, token=TOKEN)
    return lot


def test_anyone_reads_it_without_a_session(anonymous_client, sold):
    response = anonymous_client.get(URL)

    assert response.status_code == 200
    assert response.data["origin"]["farm"] == "La Esperanza"
    assert [stage["kind"] for stage in response.data["stages"]][-1] == "stock_entry"
    assert response.data["quality"]["well_fermented_pct"] == "78.5"


def keys_in(value):
    if isinstance(value, dict):
        return set(value) | set().union(*(keys_in(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(keys_in(item) for item in value))
    return set()


def test_nothing_private_appears_anywhere_in_the_response(anonymous_client, journey, sold):
    producer = journey.producer
    collector = sold.harvest.collector
    buyer = sold.sale_lines.select_related("sale__buyer").first().sale.buyer
    private_values = [
        buyer.name,
        buyer.identity_document,
        producer.member_code,
        producer.first_name,
        producer.last_name,
        producer.identity_document,
        sold.code,
        collector.email,
        collector.first_name,
        journey.owner.email,
        sold.fermentation.facility.name,
        sold.drying.facility.name,
        sold.stock_entry.warehouse.name,
    ]
    private_keys = {
        "buyer",
        "price_per_kg",
        "subtotal",
        "total",
        "code",
        "member_code",
        "producer",
        "collector",
        "responsible",
        "facility",
        "warehouse",
        "green_weight_kg",
        "dry_weight_kg",
        "g1_kg",
        "temperature_c",
        "ph",
    }

    data = anonymous_client.get(URL).data
    body = json.dumps(data, ensure_ascii=False)

    # Un dato vacío en las fábricas no prueba nada: se cuentan los que sí tienen valor.
    filled = [value for value in private_values if value]
    assert len(filled) >= 10
    for value in filled:
        assert value not in body, value
    assert not private_keys & keys_in(data)


@pytest.mark.parametrize("token", ["Xq3k9Lm2Pz7tRw1b", "corto", "Xq3k9Lm2Pz7tRw1!", "a" * 40])
def test_every_invalid_token_gets_the_same_not_found(anonymous_client, sold, token):
    response = anonymous_client.get(f"/api/public/lots/{token}")

    assert response.status_code == 404
    assert response.data == {
        "detail": "El lote no existe.",
        "code": "not_found",
        "fields": {},
    }


def test_a_session_does_not_change_the_answer(anonymous_client, auth_client, journey, sold):
    with_session = auth_client(journey.owner).get(URL)
    stranger = auth_client(UserFactory()).get(URL)

    assert with_session.status_code == stranger.status_code == 200
    assert with_session.data == stranger.data == anonymous_client.get(URL).data


def test_an_expired_session_cookie_is_ignored(anonymous_client, sold):
    anonymous_client.cookies["cacao_access"] = "basura"

    assert anonymous_client.get(URL).status_code == 200


def test_only_reading_is_allowed(anonymous_client, sold):
    assert anonymous_client.post(URL, {}, format="json").status_code == 405


def test_the_page_can_be_cached_for_five_minutes_but_a_miss_cannot(anonymous_client, sold):
    found = anonymous_client.get(URL)
    missing = anonymous_client.get("/api/public/lots/Xq3k9Lm2Pz7tRw1b")

    assert found["Cache-Control"] == "public, max-age=300"
    assert "no-store" in missing["Cache-Control"]


def test_too_many_requests_from_one_address_are_refused(anonymous_client, sold):
    for _ in range(PublicTraceabilityThrottle().num_requests):
        assert anonymous_client.get(URL).status_code == 200

    response = anonymous_client.get(URL)

    assert (response.status_code, response.data["code"]) == (429, "throttled")
