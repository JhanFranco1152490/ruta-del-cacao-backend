"""Las ventas en la bitácora: lo registrado con sus nombres, la anulación y el soporte."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.common.contracts.audit_log import audit_source
from apps.sales.models import Sale, SaleAuditEvent

from .helpers import Market

pytestmark = pytest.mark.django_db

URL = "/api/sales"
PDF = b"%PDF-1.7\n" + b"factura" * 200


@pytest.fixture
def market():
    return Market()


@pytest.fixture
def sale(auth_client, market):
    response = auth_client(market.owner).post(URL, market.body(), format="json")
    assert response.status_code == 201, response.data
    return Sale.objects.get(pk=response.data["id"])


def _entry(sale, action):
    event = SaleAuditEvent.objects.get(sale=sale, action=action)
    [entry] = audit_source("sale").describe([event.pk])
    return entry


def test_a_registered_sale_shows_its_farm_buyer_and_lines_by_name(sale):
    entry = _entry(sale, "created")

    assert (entry.record_label, entry.action_label) == (sale.code, "Venta registrada")
    changes = {change.field: change for change in entry.changes}
    assert changes["farm"].after == sale.farm.name
    assert changes["buyer"].after == sale.buyer.name
    assert changes["sale_date"].kind == "date"
    line = sale.lines.select_related("lot").first()
    assert f"{line.lot.code} · {line.get_grade_display()} · {line.quantity_kg} kg" in (
        changes["lines"].after
    )


def test_a_replaced_invoice_shows_its_names_but_not_the_internal_file(auth_client, market, sale):
    client = auth_client(market.owner)
    for name in ("factura-1.pdf", "factura-2.pdf"):
        file = SimpleUploadedFile(name, PDF, content_type="application/pdf")
        assert client.put(f"{URL}/{sale.pk}/invoice", {"file": file}, format="multipart")

    changes = {change.field: change for change in _entry(sale, "invoice_replaced").changes}

    assert "invoice" not in changes
    assert (changes["invoice_name"].before, changes["invoice_name"].after) == (
        "factura-1.pdf",
        "factura-2.pdf",
    )
