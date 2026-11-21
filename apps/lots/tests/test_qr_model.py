import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from apps.accounts import registry
from apps.accounts.system_roles import (
    ADMINISTRATOR,
    FOREMAN,
    PRODUCER,
    QUALITY_MANAGER,
    SALES_MANAGER,
    get_system_role,
)
from apps.lots.models import LotQrCode
from apps.lots.tests.factories import LotQrCodeFactory

pytestmark = pytest.mark.django_db

QR_PERMISSION = "lots.add_lotqrcode"


def test_a_lot_has_a_single_qr_code():
    qr = LotQrCodeFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        LotQrCodeFactory(lot=qr.lot)


def test_the_token_is_unique():
    qr = LotQrCodeFactory()

    with pytest.raises(IntegrityError), transaction.atomic():
        LotQrCodeFactory(token=qr.token)


def test_the_qr_code_is_found_from_its_lot():
    qr = LotQrCodeFactory()

    assert qr.lot.qr_code == qr


def test_a_lot_with_a_qr_code_cannot_be_deleted():
    qr = LotQrCodeFactory()

    with pytest.raises(ProtectedError):
        qr.lot.delete()


def test_the_qr_code_survives_the_account_that_generated_it():
    qr = LotQrCodeFactory()

    qr.created_by.delete()
    qr.refresh_from_db()

    assert qr.created_by is None


def test_the_only_permission_is_to_generate_it():
    codes = {codename for codename, _ in LotQrCode._meta.permissions}

    assert codes == {"add_lotqrcode"}
    assert LotQrCode._meta.default_permissions == ()


def test_generating_is_delegable_and_a_field_permission():
    assert registry.is_delegable(QR_PERMISSION)
    assert registry.is_field_permission(QR_PERMISSION)
    assert registry.area_of(QR_PERMISSION) == "lots"


def test_generating_needs_to_see_lots():
    assert registry.PERMISSION_DEPENDENCIES[QR_PERMISSION] == "lots.view_lot"


def test_only_the_producer_generates_by_default():
    assert QR_PERMISSION in get_system_role(PRODUCER).permission_codes
    for role in (ADMINISTRATOR, FOREMAN, QUALITY_MANAGER, SALES_MANAGER):
        assert QR_PERMISSION not in get_system_role(role).permission_codes
