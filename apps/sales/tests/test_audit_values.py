"""Los valores en el historial de la venta: lo registrado, la anulación y el soporte."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

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


def _event(sale, action):
    return SaleAuditEvent.objects.get(sale=sale, action=action)


def test_the_registration_keeps_its_farm_buyer_date_and_lines(sale):
    changes = _event(sale, "created").changes

    assert changes["farm"] == {"before": None, "after": str(sale.farm_id)}
    assert changes["buyer"] == {"before": None, "after": str(sale.buyer_id)}
    assert changes["sale_date"]["after"] == sale.sale_date.isoformat()
    line = sale.lines.select_related("lot").first()
    assert {
        "lot": line.lot.code,
        "grade": line.grade,
        "quantity_kg": str(line.quantity_kg),
        "price_per_kg": line.price_per_kg,
    } in changes["lines"]["after"]


def test_voiding_keeps_the_reason(auth_client, market, sale):
    response = auth_client(market.owner).post(
        f"{URL}/{sale.pk}/void",
        {"expected_version": sale.version, "reason": "Error de digitación"},
        format="json",
    )
    assert response.status_code == 200, response.data

    changes = _event(sale, "voided").changes
    assert changes["void_reason"] == {"before": "", "after": "Error de digitación"}
    assert changes["voided_by"]["after"] == str(market.owner.pk)


def test_the_invoice_keeps_its_file_name_before_and_after(auth_client, market, sale):
    client = auth_client(market.owner)
    for name in ("factura-1.pdf", "factura-2.pdf"):
        file = SimpleUploadedFile(name, PDF, content_type="application/pdf")
        response = client.put(f"{URL}/{sale.pk}/invoice", {"file": file}, format="multipart")
        assert response.status_code == 200, response.data

    replaced = _event(sale, "invoice_replaced")
    assert replaced.changes["invoice_name"] == {
        "before": "factura-1.pdf",
        "after": "factura-2.pdf",
    }
    # El nombre con que se guarda el archivo es interno: no va en el historial.
    assert "invoice" not in replaced.changes
