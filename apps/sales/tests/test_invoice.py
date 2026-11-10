import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.role_helpers import make_delegate
from apps.sales.models import INVOICE_MAX_BYTES, Sale, SaleAuditEvent

from .helpers import Market

pytestmark = pytest.mark.django_db

URL = "/api/sales"
PDF = b"%PDF-1.7\n" + b"factura" * 200
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"foto" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"foto" * 200


@pytest.fixture
def market():
    return Market()


@pytest.fixture
def sale(auth_client, market):
    response = auth_client(market.owner).post(URL, market.body(), format="json")
    assert response.status_code == 201, response.data
    return Sale.objects.get(pk=response.data["id"])


def invoice_url(sale) -> str:
    return f"{URL}/{sale.pk}/invoice"


def document(content=PDF, name="factura-1043.pdf"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def attach(client, sale, file=None):
    return client.put(invoice_url(sale), {"file": file or document()}, format="multipart")


def actions(sale) -> list[str]:
    return list(
        SaleAuditEvent.objects.filter(sale=sale)
        .order_by("occurred_at")
        .values_list("action", flat=True)
    )


@pytest.mark.parametrize(
    "content, content_type, name",
    [
        (PDF, "application/pdf", "factura.pdf"),
        (JPEG, "image/jpeg", "factura.jpg"),
        (PNG, "image/png", "factura.png"),
    ],
)
def test_a_pdf_jpg_or_png_is_attached(auth_client, market, sale, content, content_type, name):
    response = attach(auth_client(market.owner), sale, document(content, name))

    assert response.status_code == 200, response.data
    invoice = response.data["invoice"]
    assert (invoice["file_name"], invoice["content_type"]) == (name, content_type)
    assert invoice["size"] == len(content)
    assert response.data["version"] == 2
    sale.refresh_from_db()
    # El nombre en el almacenamiento lo pone el servidor.
    assert sale.invoice.name.startswith(f"sales/{sale.pk}")
    assert actions(sale) == ["created", "invoice_attached"]


def test_the_name_sent_does_not_decide_the_format(auth_client, market, sale):
    response = attach(auth_client(market.owner), sale, document(b"PK\x03\x04docx", "f.pdf"))

    assert response.status_code == 415
    assert response.data["code"] == "invoice_format_not_allowed"
    assert response.data["detail"] == "Solo se permiten PDF, JPG o PNG."


def test_five_megabytes_are_accepted_and_one_byte_more_is_not(auth_client, market, sale):
    client = auth_client(market.owner)
    exact = PDF + b"x" * (INVOICE_MAX_BYTES - len(PDF))
    over = exact + b"x"

    assert attach(client, sale, document(over)).status_code == 413
    assert attach(client, sale, document(exact)).status_code == 200


def test_too_large_says_why(auth_client, market, sale):
    over = PDF + b"x" * INVOICE_MAX_BYTES

    response = attach(auth_client(market.owner), sale, document(over))

    assert response.data["code"] == "invoice_too_large"
    assert response.data["detail"] == "El archivo supera el tamaño máximo de 5 MB."


def test_without_a_file_it_is_a_400(auth_client, market, sale):
    response = auth_client(market.owner).put(invoice_url(sale), {}, format="multipart")

    assert response.status_code == 400
    assert "file" in response.data["fields"]


def test_replacing_keeps_only_the_new_file(
    auth_client, market, sale, django_capture_on_commit_callbacks
):
    client = auth_client(market.owner)
    attach(client, sale)
    sale.refresh_from_db()
    first = sale.invoice.name

    with django_capture_on_commit_callbacks(execute=True):
        response = attach(client, sale, document(JPEG, "foto.jpg"))

    assert response.data["invoice"]["file_name"] == "foto.jpg"
    assert not default_storage.exists(first)
    assert actions(sale) == ["created", "invoice_attached", "invoice_replaced"]


def test_removing_leaves_the_sale_without_a_document(
    auth_client, market, sale, django_capture_on_commit_callbacks
):
    client = auth_client(market.owner)
    attach(client, sale)
    sale.refresh_from_db()
    stored = sale.invoice.name

    with django_capture_on_commit_callbacks(execute=True):
        response = client.delete(invoice_url(sale))

    assert response.status_code == 204
    sale.refresh_from_db()
    assert not sale.invoice
    assert not default_storage.exists(stored)
    assert actions(sale)[-1] == "invoice_removed"
    assert client.get(f"{URL}/{sale.pk}").data["invoice"] is None


def test_removing_when_there_is_none_changes_nothing(auth_client, market, sale):
    response = auth_client(market.owner).delete(invoice_url(sale))

    assert response.status_code == 204
    assert actions(sale) == ["created"]


def test_the_file_is_downloaded_with_its_type_and_name(auth_client, market, sale):
    client = auth_client(market.owner)
    attach(client, sale)

    response = client.get(invoice_url(sale))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "factura-1043.pdf" in response["Content-Disposition"]
    assert response["X-Content-Type-Options"] == "nosniff"
    assert b"".join(response.streaming_content) == PDF


def test_without_a_document_there_is_nothing_to_download(auth_client, market, sale):
    assert auth_client(market.owner).get(invoice_url(sale)).status_code == 404


def test_a_voided_sale_keeps_its_document_but_it_does_not_change(auth_client, market, sale):
    client = auth_client(market.owner)
    attach(client, sale)
    sale.refresh_from_db()
    client.post(
        f"{URL}/{sale.pk}/void",
        {"reason": "Cancelada", "expected_version": sale.version},
        format="json",
    )

    assert attach(client, sale).data["code"] == "sale_voided"
    assert client.delete(invoice_url(sale)).data["code"] == "sale_voided"
    assert client.get(invoice_url(sale)).status_code == 200


def test_attaching_needs_the_permission_to_register_and_the_farm(
    auth_client, anonymous_client, market, sale
):
    viewer = make_delegate(market.producer, ["sales.view_sale"], farm=market.farm)
    elsewhere = make_delegate(market.producer, ["sales.add_sale"], farm=market.other_farm)

    assert attach(anonymous_client, sale).status_code == 401
    assert attach(auth_client(viewer), sale).status_code == 403
    assert auth_client(viewer).delete(invoice_url(sale)).status_code == 403
    assert attach(auth_client(elsewhere), sale).status_code == 404


def test_downloading_needs_to_reach_the_sale(auth_client, market, sale):
    attach(auth_client(market.owner), sale)
    viewer = make_delegate(market.producer, ["sales.view_sale"], farm=market.farm)
    elsewhere = make_delegate(market.producer, ["sales.view_sale"], farm=market.other_farm)

    assert auth_client(viewer).get(invoice_url(sale)).status_code == 200
    assert auth_client(elsewhere).get(invoice_url(sale)).status_code == 404


def stored_invoices() -> set[str]:
    try:
        return set(default_storage.listdir("sales")[1])
    except FileNotFoundError:
        return set()


def test_a_voided_sale_leaves_no_file_behind(auth_client, market, sale):
    client = auth_client(market.owner)
    client.post(
        f"{URL}/{sale.pk}/void",
        {"expected_version": sale.version, "reason": "Error de digitación"},
        format="json",
    )
    before = stored_invoices()

    response = attach(client, sale)

    assert response.status_code == 409
    assert stored_invoices() == before


def test_a_sale_that_is_not_reached_leaves_no_file_behind(auth_client, market, sale):
    other = Market()
    before = stored_invoices()

    response = attach(auth_client(other.owner), sale)

    assert response.status_code == 404
    assert stored_invoices() == before


def test_a_failed_registration_deletes_the_file_it_already_stored(
    auth_client, market, sale, monkeypatch
):
    from apps.sales.exceptions import SaleVoided
    from apps.sales.services import invoice

    def fail(*args, **kwargs):
        raise SaleVoided()

    monkeypatch.setattr(invoice, "_register_invoice", fail)
    before = stored_invoices()

    response = attach(auth_client(market.owner), sale)

    assert response.status_code == 409
    assert stored_invoices() == before
