"""La bitácora por la API: lo más reciente primero, los filtros, quién la consulta y la paginación
entre los historiales de distintas apps."""

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.events import record_account_event
from apps.accounts.models import AccountManagementEvent
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tests.role_helpers import (
    make_administrator,
    make_delegate,
    make_producer_owner,
)
from apps.common.contracts.audit_log import AUDIT_RECORD_TYPES, audit_source
from apps.farms.models import FarmAuditEvent
from apps.farms.services.audit import record_farm_audit_event
from apps.farms.tests.factories import FarmFactory
from apps.producers.tests.factories import ProducerFactory
from apps.sales.models import SaleAuditEvent
from apps.sales.services.audit import record_sale_event
from apps.sales.tests.factories import SaleFactory

pytestmark = pytest.mark.django_db

URL = "/api/audit-log"
BOGOTA = ZoneInfo("America/Bogota")
START = datetime(2026, 11, 10, 9, 0, tzinfo=BOGOTA)


class Estate:
    """Un productor con su finca, su dueño y un empleado, y eventos de fincas y de ventas en
    horas conocidas."""

    def __init__(self):
        self.producer = ProducerFactory()
        self.owner = make_producer_owner(self.producer)
        self.farm = FarmFactory(producer=self.producer, name="La Esperanza")
        self.employee = UserFactory(producer=self.producer, first_name="Luis", last_name="Peña")

    def farm_event(self, hours, actor=None):
        event = record_farm_audit_event(
            farm=self.farm, actor=actor or self.owner, action="updated", changed_fields=["name"]
        )
        FarmAuditEvent.objects.filter(pk=event.pk).update(
            occurred_at=START + timedelta(hours=hours)
        )
        return event

    def sale_event(self, hours, actor=None):
        sale = SaleFactory(farm=self.farm, producer=self.producer)
        event = record_sale_event(
            sale=sale, actor=actor or self.owner, action="voided", changed_fields=["void_reason"]
        )
        SaleAuditEvent.objects.filter(pk=event.pk).update(
            occurred_at=START + timedelta(hours=hours)
        )
        return event


@pytest.fixture
def estate():
    return Estate()


def ids(response):
    assert response.status_code == 200, response.data
    return [row["id"] for row in response.data["results"]]


def test_the_most_recent_comes_first_with_its_shape(auth_client, estate):
    older = estate.farm_event(0)
    newer = estate.sale_event(2, actor=estate.employee)

    response = auth_client(estate.owner).get(URL)

    assert ids(response) == [str(newer.pk), str(older.pk)]
    first = response.data["results"][0]
    assert first["record_type"] == "sale"
    assert first["record_type_label"] == "Venta"
    assert first["actor"] == {"id": str(estate.employee.pk), "full_name": "Luis Peña"}
    assert first["action"] == "voided"
    assert first["action_label"] == "Venta anulada"
    assert set(first["record"]) == {"id", "label", "deleted"}
    assert set(first["changes"][0]) == {"field", "label", "kind", "before", "after", "hidden"}
    assert response.data["count"] == 2


def test_filtering_by_user_type_and_period(auth_client, estate):
    by_owner = estate.farm_event(0)
    by_employee = estate.farm_event(30, actor=estate.employee)
    sale = estate.sale_event(31, actor=estate.employee)
    client = auth_client(estate.owner)

    assert set(ids(client.get(URL, {"actor": str(estate.employee.pk)}))) == {
        str(by_employee.pk),
        str(sale.pk),
    }
    assert ids(client.get(URL, {"record_type": "farm"})) == [str(by_employee.pk), str(by_owner.pk)]
    # El 10 en Bogotá: solo el primero; el 11 trae los dos de la tarde siguiente.
    assert ids(client.get(URL, {"from": "2026-11-10", "to": "2026-11-10"})) == [str(by_owner.pk)]
    assert ids(
        client.get(
            URL, {"from": "2026-11-11", "record_type": "sale", "actor": str(estate.employee.pk)}
        )
    ) == [str(sale.pk)]


def test_no_results_is_an_empty_list(auth_client, estate):
    estate.farm_event(0)

    response = auth_client(estate.owner).get(URL, {"record_type": "harvest"})

    assert (response.data["count"], response.data["results"]) == (0, [])


def test_the_end_cannot_be_before_the_start(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"from": "2026-11-10", "to": "2026-11-09"})

    assert (response.status_code, response.data["code"]) == (400, "validation_error")
    assert "to" in response.data["fields"]


def test_an_unknown_record_type_is_rejected(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"record_type": "pest"})

    assert response.status_code == 400
    assert "record_type" in response.data["fields"]


def test_an_account_of_another_producer_is_not_found(auth_client, estate):
    response = auth_client(estate.owner).get(URL, {"actor": str(UserFactory().pk)})

    assert (response.status_code, response.data["code"]) == (404, "not_found")
    assert "actor" in response.data["fields"]


def test_nothing_of_another_producer_comes_out(auth_client, estate):
    mine = estate.farm_event(0)
    record_farm_audit_event(farm=FarmFactory(), actor=None, action="updated")

    assert ids(auth_client(estate.owner).get(URL)) == [str(mine.pk)]


def test_an_employee_with_every_delegable_permission_and_the_association_cannot_enter(
    auth_client, estate
):
    employee = make_delegate(
        estate.producer, ["farms.view_farm", "sales.view_sale"], all_farms=True
    )

    for account in (employee, make_administrator()):
        response = auth_client(account).get(URL)
        assert (response.status_code, response.data["code"]) == (403, "permission_denied")


def test_the_technical_account_chooses_the_producer(auth_client, estate):
    event = estate.farm_event(0)
    technical = auth_client(UserFactory(is_superuser=True))

    assert ids(technical.get(URL, {"producer": str(estate.producer.pk)})) == [str(event.pk)]
    missing = technical.get(URL)
    assert (missing.status_code, "producer" in missing.data["fields"]) == (400, True)
    unknown = technical.get(URL, {"producer": str(uuid.uuid4())})
    assert (unknown.status_code, "producer" in unknown.data["fields"]) == (404, True)


def test_the_pages_mix_record_types_without_repeating_or_skipping(auth_client, estate):
    events = [
        estate.farm_event(0),
        estate.sale_event(1),
        estate.farm_event(2),
        estate.sale_event(3),
        estate.farm_event(4),
        estate.sale_event(5),
    ]
    newest_first = [str(event.pk) for event in reversed(events)]
    client = auth_client(estate.owner)

    first = ids(client.get(URL, {"page_size": 4}))
    second = ids(client.get(URL, {"page_size": 4, "page": 2}))

    assert first + second == newest_first


def test_the_queries_do_not_grow_with_the_events(auth_client, estate):
    client = auth_client(estate.owner)

    def queries():
        with CaptureQueriesContext(connection) as context:
            assert client.get(URL, {"page_size": 100}).status_code == 200
        return len(context.captured_queries)

    for hours in range(5):
        estate.farm_event(hours)
        estate.sale_event(hours)
    few = queries()
    for hours in range(5, 30):
        estate.farm_event(hours)
        estate.sale_event(hours)
        record_account_event(
            AccountManagementEvent.EventType.ACCOUNT_DEACTIVATED,
            uuid.uuid4(),
            actor=estate.owner,
            target_user=estate.employee,
        )

    # Con un tipo más en la página, a lo sumo sus consultas de traducción.
    assert queries() <= few + 2


def test_the_options_bring_the_accounts_and_the_record_types(auth_client, estate):
    response = auth_client(estate.owner).get(f"{URL}/options")

    assert response.status_code == 200
    names = [actor["full_name"] for actor in response.data["actors"]]
    assert "Luis Peña" in names
    assert [kind["value"] for kind in response.data["record_types"]] == list(AUDIT_RECORD_TYPES)
    assert response.data["record_types"][0] == {"value": "farm", "label": "Finca"}


def test_every_record_type_was_registered_by_its_app():
    for record_type in AUDIT_RECORD_TYPES:
        assert audit_source(record_type)
