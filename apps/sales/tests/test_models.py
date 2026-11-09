from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.buyers.exceptions import BuyerHasRecords
from apps.buyers.services import delete_buyer
from apps.sales.models import (
    INVOICE_MAX_BYTES,
    MAX_LINES,
    MAX_PRICE_PER_KG,
    Sale,
    SaleAuditEvent,
    SaleCodeSequence,
)

from .factories import SaleFactory, SaleLineFactory

pytestmark = pytest.mark.django_db


def test_the_limits_are_the_ones_of_the_story():
    assert (MAX_LINES, MAX_PRICE_PER_KG, INVOICE_MAX_BYTES) == (20, 1_000_000, 5 * 1024 * 1024)


def test_the_code_is_the_number_with_at_least_four_digits():
    assert SaleFactory.build(number=12).code == "V-0012"
    assert SaleFactory.build(number=12345).code == "V-12345"


def test_the_status_comes_from_the_void_mark():
    sale = SaleFactory()
    assert sale.status == Sale.Status.REGISTERED

    sale.voided_by = sale.created_by
    sale.voided_at = timezone.now()
    sale.void_reason = "Error de digitación"
    assert sale.status == Sale.Status.VOIDED


def test_the_number_is_unique_per_producer():
    sale = SaleFactory(number=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        SaleFactory(farm=sale.farm, number=1)

    SaleFactory(number=1)


def test_a_void_mark_is_complete_or_absent():
    with pytest.raises(IntegrityError), transaction.atomic():
        SaleFactory(voided_at=timezone.now())


def test_the_invoice_data_go_together():
    with pytest.raises(IntegrityError), transaction.atomic():
        SaleFactory(invoice="sales/x.pdf")

    SaleFactory(
        invoice="sales/x.pdf",
        invoice_name="factura.pdf",
        invoice_content_type="application/pdf",
        invoice_size=1024,
        invoice_uploaded_at=timezone.now(),
    )


def test_a_lot_and_grade_appear_once_per_sale():
    line = SaleLineFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        SaleLineFactory(sale=line.sale, stock_exit__lot=line.lot, stock_exit__grade=line.grade)

    SaleLineFactory(sale=line.sale, stock_exit__lot=line.lot, stock_exit__grade="g2")


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity_kg": Decimal("0.0")},
        {"price_per_kg": 0},
        {"price_per_kg": MAX_PRICE_PER_KG + 1},
        {"subtotal": -1},
    ],
)
def test_a_line_keeps_its_amounts_in_range(changes):
    with pytest.raises(IntegrityError), transaction.atomic():
        SaleLineFactory(**changes)


def test_the_highest_price_is_accepted():
    SaleLineFactory(price_per_kg=MAX_PRICE_PER_KG)


def test_a_stock_exit_belongs_to_one_line_only():
    line = SaleLineFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        SaleLineFactory(stock_exit=line.stock_exit)


def test_what_a_sale_points_to_is_protected():
    line = SaleLineFactory()
    sale = line.sale

    for record in (sale.farm, sale.buyer, line.lot, line.stock_exit, sale.created_by):
        with pytest.raises(ProtectedError), transaction.atomic():
            record.delete()


def test_a_buyer_with_a_sale_is_not_deleted():
    sale = SaleFactory()
    owner = UserFactory(producer=sale.producer)

    with pytest.raises(BuyerHasRecords):
        delete_buyer(owner, sale.buyer.pk, sale.buyer.version)


def test_the_sequence_is_one_per_producer():
    sale = SaleFactory()
    SaleCodeSequence.objects.create(producer=sale.producer, last_value=1)

    with pytest.raises(IntegrityError), transaction.atomic():
        SaleCodeSequence.objects.create(producer=sale.producer, last_value=2)


def test_the_audit_event_keeps_no_values():
    stored = {field.name for field in SaleAuditEvent._meta.get_fields()}

    assert "changes" not in stored
    assert SaleAuditEvent.Action.values == [
        "created",
        "voided",
        "invoice_attached",
        "invoice_replaced",
        "invoice_removed",
    ]
